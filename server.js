const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFile } = require("child_process");
const PDFDocument = require("pdfkit");
const { MongoClient, ServerApiVersion } = require("mongodb");

const HOST = "0.0.0.0";
const ROOT_DIR = __dirname;
const PDFCODE_DIR = path.join(ROOT_DIR, "pdfcode");
const PDF_CONNECTOR_SCRIPT_PATH = path.join(PDFCODE_DIR, "generate_from_mock_data.py");
const DEFAULT_PDF_LOGO_PATH = path.join(PDFCODE_DIR, "image", "extracted-000.jpg");
const ROLL_FIELD_ALIASES = ["rollNo", "University_RollNo", "universityRollNo", "RollNo", "roll_no", "UniversityRollNo"];

const ROUTE_ALIAS = "/Exam/Report/DownloadGradesheet.aspx";
const ROUTE_PREFIX = "/Exam/Report/";
const REQUEST_BODY_LIMIT_BYTES = 1024 * 1024;
const PDF_ENGINE_ALLOWED_VALUES = new Set(["auto", "python", "node"]);

let mongoClientPromise = null;
let mongoClientInstance = null;
let cachedMongoConfig = null;
let cachedMongoClientOptions = null;

const MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webp": "image/webp"
};

function logInfo(message) {
    console.log(`[${new Date().toISOString()}] INFO ${message}`);
}

function logWarn(message) {
    console.warn(`[${new Date().toISOString()}] WARN ${message}`);
}

function logError(message) {
    console.error(`[${new Date().toISOString()}] ERROR ${message}`);
}

function loadEnvFileIfPresent(filePath) {
    let content = "";
    try {
        content = fs.readFileSync(filePath, "utf-8");
    } catch {
        return;
    }

    for (const rawLine of content.split(/\r?\n/)) {
        const line = rawLine.trim();
        if (!line || line.startsWith("#")) {
            continue;
        }

        const separatorIndex = line.indexOf("=");
        if (separatorIndex <= 0) {
            continue;
        }

        const key = line.slice(0, separatorIndex).trim();
        let value = line.slice(separatorIndex + 1).trim();

        const wrappedWithSingleQuotes = value.startsWith("'") && value.endsWith("'") && value.length >= 2;
        const wrappedWithDoubleQuotes = value.startsWith("\"") && value.endsWith("\"") && value.length >= 2;

        if (wrappedWithSingleQuotes || wrappedWithDoubleQuotes) {
            value = value.slice(1, -1);
        }

        if (!(key in process.env)) {
            process.env[key] = value;
        }
    }
}

function loadLocalEnv() {
    const envCandidates = [
        path.join(ROOT_DIR, ".env"),
        path.join(process.cwd(), ".env")
    ];

    const visited = new Set();
    for (const envPath of envCandidates) {
        const resolvedPath = path.resolve(envPath);
        if (visited.has(resolvedPath)) {
            continue;
        }

        visited.add(resolvedPath);
        loadEnvFileIfPresent(resolvedPath);
    }
}

function isAtlasSqlQueryEndpoint(uri) {
    try {
        const parsed = new URL(uri);
        return parsed.hostname.startsWith("atlas-sql-") || parsed.hostname.endsWith(".query.mongodb.net");
    } catch {
        return false;
    }
}

function getRequiredEnvValue(name) {
    const value = String(process.env[name] || "").trim();
    if (!value) {
        throw new Error(`Missing required environment variable: ${name}`);
    }
    return value;
}

function getIntegerEnv(name, defaultValue, minimum, maximum) {
    const rawValue = String(process.env[name] || "").trim();
    if (!rawValue) {
        return defaultValue;
    }

    const parsedValue = Number(rawValue);
    if (!Number.isInteger(parsedValue) || parsedValue < minimum || parsedValue > maximum) {
        throw new Error(`${name} must be an integer between ${minimum} and ${maximum}. Received: ${rawValue}`);
    }

    return parsedValue;
}

function getPortFromEnv() {
    const rawPort = String(process.env.PORT || "").trim();
    if (!rawPort) {
        return 5500;
    }

    const parsedPort = Number(rawPort);
    if (!Number.isInteger(parsedPort) || parsedPort <= 0 || parsedPort > 65535) {
        throw new Error(`Invalid PORT value: ${rawPort}. PORT must be a number between 1 and 65535.`);
    }

    return parsedPort;
}

function getPdfEngine() {
    const rawEngine = String(process.env.PDF_ENGINE || "auto").trim().toLowerCase();
    if (!PDF_ENGINE_ALLOWED_VALUES.has(rawEngine)) {
        throw new Error(`Invalid PDF_ENGINE value: ${rawEngine}. Allowed values: auto, python, node.`);
    }
    return rawEngine;
}

function getMongoClientOptions() {
    // Assumption: this service is a long-running Render web process with moderate API concurrency.
    const maxPoolSize = getIntegerEnv("MONGODB_MAX_POOL_SIZE", 20, 1, 500);
    const minPoolSize = getIntegerEnv("MONGODB_MIN_POOL_SIZE", 2, 0, 100);

    if (minPoolSize > maxPoolSize) {
        throw new Error("MONGODB_MIN_POOL_SIZE cannot be greater than MONGODB_MAX_POOL_SIZE.");
    }

    return {
        maxPoolSize: maxPoolSize,
        minPoolSize: minPoolSize,
        maxIdleTimeMS: getIntegerEnv("MONGODB_MAX_IDLE_TIME_MS", 30000, 1000, 600000),
        connectTimeoutMS: getIntegerEnv("MONGODB_CONNECT_TIMEOUT_MS", 10000, 1000, 120000),
        serverSelectionTimeoutMS: getIntegerEnv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", 10000, 1000, 120000),
        socketTimeoutMS: getIntegerEnv("MONGODB_SOCKET_TIMEOUT_MS", 45000, 1000, 300000)
    };
}

function getMongoConfig() {
    const uri = getRequiredEnvValue("MONGODB_URI");
    const dbName = getRequiredEnvValue("MONGODB_DB");
    const collectionName = getRequiredEnvValue("MONGODB_COLLECTION");

    if (uri.includes("<db_password>") || uri.includes("<username>")) {
        throw new Error("Set MONGODB_URI with your real Atlas credentials before running the server.");
    }

    if (isAtlasSqlQueryEndpoint(uri)) {
        throw new Error("MONGODB_URI points to Atlas SQL endpoint. Use your Atlas cluster URI (mongodb+srv://...mongodb.net/...).");
    }

    return { uri, dbName, collectionName };
}

async function getMongoCollection() {
    const config = cachedMongoConfig || getMongoConfig();
    const mongoOptions = cachedMongoClientOptions || getMongoClientOptions();

    if (!mongoClientPromise) {
        mongoClientPromise = (async function () {
            // Keep connection setup aligned with the Atlas snippet: connect first, then ping admin.
            const client = new MongoClient(config.uri, {
                serverApi: {
                    version: ServerApiVersion.v1,
                    strict: true,
                    deprecationErrors: true
                },
                retryReads: true,
                retryWrites: true,
                maxPoolSize: mongoOptions.maxPoolSize,
                minPoolSize: mongoOptions.minPoolSize,
                maxIdleTimeMS: mongoOptions.maxIdleTimeMS,
                connectTimeoutMS: mongoOptions.connectTimeoutMS,
                serverSelectionTimeoutMS: mongoOptions.serverSelectionTimeoutMS,
                socketTimeoutMS: mongoOptions.socketTimeoutMS
            });

            await client.connect();
            await client.db("admin").command({ ping: 1 });
            mongoClientInstance = client;
            logInfo(`Connected to MongoDB database "${config.dbName}".`);
            return client;
        })()
            .catch(function (error) {
                mongoClientPromise = null;
                logError(`MongoDB connection failed: ${error.message}`);
                throw error;
            });
    }

    const client = await mongoClientPromise;
    return client.db(config.dbName).collection(config.collectionName);
}

async function closeMongoClient() {
    if (!mongoClientInstance) {
        return;
    }

    const activeClient = mongoClientInstance;
    mongoClientInstance = null;
    mongoClientPromise = null;
    await activeClient.close();
}

function normalizeMongoStudentDocument(document) {
    const normalized = { ...document };
    delete normalized._id;

    if (!normalized.rollNo) {
        normalized.rollNo = normalized.University_RollNo || normalized.universityRollNo || normalized.RollNo || normalized.roll_no || "";
    }

    if (!normalized.fatherName) {
        normalized.fatherName = normalized.Father_Name || normalized.father_name || "";
    }

    if (!normalized.motherName) {
        normalized.motherName = normalized.Mother_Name || normalized.mother_name || "";
    }

    if (!normalized.studentName) {
        normalized.studentName = normalized.Student_Name || normalized.student_name || "";
    }

    if (!normalized.enrollmentNo) {
        normalized.enrollmentNo = normalized.Enrollment_No || normalized.EnrollmentNo || normalized.enrollment_no || "";
    }

    return normalized;
}

loadLocalEnv();

const PDF_FALLBACK_TO_NODE = process.env.PDF_FALLBACK_TO_NODE !== "false";
let PORT = 5500;
let PDF_ENGINE = "auto";

try {
    PORT = getPortFromEnv();
    PDF_ENGINE = getPdfEngine();
    cachedMongoConfig = getMongoConfig();
    cachedMongoClientOptions = getMongoClientOptions();
} catch (error) {
    logError(`Configuration error: ${error.message}`);
    process.exit(1);
}

function sendJson(res, statusCode, payload) {
    res.writeHead(statusCode, {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff"
    });
    res.end(JSON.stringify(payload));
}

function sendApiError(res, statusCode, message, code) {
    sendJson(res, statusCode, {
        success: false,
        code: code || "API_ERROR",
        message: message
    });
}

function readRequestBody(req) {
    return new Promise(function (resolve, reject) {
        let rawBody = "";
        let settled = false;

        function fail(error) {
            if (settled) {
                return;
            }
            settled = true;
            reject(error);
        }

        function succeed(value) {
            if (settled) {
                return;
            }
            settled = true;
            resolve(value);
        }

        req.on("data", function (chunk) {
            if (settled) {
                return;
            }

            rawBody += chunk;
            if (rawBody.length > REQUEST_BODY_LIMIT_BYTES) {
                fail(new Error("Request body is too large"));
                req.destroy();
            }
        });

        req.on("end", function () {
            if (settled) {
                return;
            }

            if (!rawBody.trim()) {
                succeed({});
                return;
            }

            try {
                succeed(JSON.parse(rawBody));
            } catch (error) {
                fail(new Error("Invalid JSON body"));
            }
        });

        req.on("error", function (error) {
            fail(error);
        });
    });
}

function sanitizeFileName(value) {
    return String(value || "gradesheet").replace(/[^a-zA-Z0-9._-]/g, "_");
}

function normalizeText(value) {
    return String(value || "").trim().toLowerCase();
}

const SHARED_RESULT_KEYS = [
    "session",
    "examCategory",
    "degree",
    "semester",
    "semesterSection",
    "universityName",
    "collegeName",
    "examName"
];

function isEmptyResultValue(value) {
    return value === undefined || value === null || (typeof value === "string" && !value.trim());
}

function normalizeResultData(parsed) {
    if (!parsed || !Array.isArray(parsed.students)) {
        return parsed;
    }

    const sharedDefaults = {};
    for (const key of SHARED_RESULT_KEYS) {
        if (!Object.prototype.hasOwnProperty.call(parsed, key)) {
            continue;
        }

        const value = parsed[key];
        if (!isEmptyResultValue(value)) {
            sharedDefaults[key] = value;
        }
    }

    if (Object.keys(sharedDefaults).length === 0) {
        return parsed;
    }

    const normalizedStudents = parsed.students.map(function (student) {
        if (!student || typeof student !== "object") {
            return student;
        }

        const merged = { ...student };
        for (const [key, value] of Object.entries(sharedDefaults)) {
            if (isEmptyResultValue(merged[key])) {
                merged[key] = value;
            }
        }

        return merged;
    });

    return {
        ...parsed,
        students: normalizedStudents
    };
}

function runExecFile(command, args, options) {
    const timeoutMs = getIntegerEnv("PDF_COMMAND_TIMEOUT_MS", 120000, 1000, 600000);
    const finalOptions = {
        windowsHide: true,
        maxBuffer: 10 * 1024 * 1024,
        timeout: timeoutMs,
        ...options
    };

    return new Promise(function (resolve, reject) {
        execFile(command, args, finalOptions, function (error, stdout, stderr) {
            if (error) {
                const message = (stderr || stdout || error.message || "Command failed").trim();
                reject(new Error(message));
                return;
            }

            resolve({ stdout: stdout || "", stderr: stderr || "" });
        });
    });
}

async function runPythonTemplateGenerator(scriptArgs, options) {
    const pythonFromEnv = (process.env.PYTHON || "").trim();
    const candidates = [];

    if (pythonFromEnv) {
        candidates.push({ command: pythonFromEnv, prefix: [] });
    }

    if (process.platform === "win32") {
        candidates.push({ command: "python", prefix: [] });
        candidates.push({ command: "py", prefix: ["-3"] });
    } else {
        candidates.push({ command: "python3", prefix: [] });
        candidates.push({ command: "python", prefix: [] });
    }

    let lastError = null;

    for (const candidate of candidates) {
        try {
            const args = candidate.prefix.concat(scriptArgs);
            await runExecFile(candidate.command, args, options);
            return;
        } catch (error) {
            lastError = error;
        }
    }

    throw lastError || new Error("No Python runtime found to execute template generator.");
}

function extractPdfcodeLogin(payload) {
    return {
        rollNo: ((payload.rollNoField || payload.rollNo || "") + "").trim(),
        fatherName: ((payload.fatherNameField || payload.fatherName || "") + "").trim()
    };
}

function extractEnteredFields(payload) {
    return {
        session: (payload.sessionField || payload.session || "").trim(),
        examCategory: (payload.examCategoryField || payload.examCategory || "").trim(),
        degree: (payload.degreeField || payload.degree || "").trim(),
        semester: (payload.semesterField || payload.semester || "").trim(),
        rollNo: (payload.rollNoField || payload.rollNo || "").trim(),
        fatherName: (payload.fatherNameField || payload.fatherName || "").trim(),
        motherName: (payload.motherNameField || payload.motherName || "").trim()
    };
}

function resolveFilePath(requestUrl) {
    const rawPath = requestUrl.split("?")[0].split("#")[0];
    let requestPath = rawPath;

    if (requestPath === ROUTE_ALIAS || requestPath === `${ROUTE_ALIAS}/`) {
        requestPath = "/";
    } else if (requestPath.startsWith(ROUTE_PREFIX)) {
        requestPath = `/${requestPath.slice(ROUTE_PREFIX.length)}`;
    }

    const requestedPath = requestPath === "/" ? "index.html" : requestPath.replace(/^\/+/, "");
    const normalizedPath = path.normalize(requestedPath);
    const absolutePath = path.join(ROOT_DIR, normalizedPath);

    const rootNormalized = path.resolve(ROOT_DIR).toLowerCase();
    const targetNormalized = path.resolve(absolutePath).toLowerCase();

    if (!targetNormalized.startsWith(rootNormalized)) {
        return null;
    }

    return absolutePath;
}

function sendFile(res, filePath) {
    const extension = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[extension] || "application/octet-stream";
    const stream = fs.createReadStream(filePath);

    const cacheControl = extension === ".html"
        ? "no-store"
        : "public, max-age=86400";

    stream.on("error", function () {
        res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("500 Internal Server Error");
    });

    res.writeHead(200, {
        "Content-Type": contentType,
        "Cache-Control": cacheControl,
        "X-Content-Type-Options": "nosniff"
    });
    stream.pipe(res);
}

function escapeRegex(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeAcademicToken(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "");
}

function buildRollSearchFilter(rawRollNo) {
    const rollNo = String(rawRollNo || "").trim();
    const canonicalRollNo = rollNo.toUpperCase();

    const stringValues = new Set();
    if (rollNo) {
        stringValues.add(rollNo);
    }
    if (canonicalRollNo) {
        stringValues.add(canonicalRollNo);
    }

    const numericValues = [];
    if (/^\d+$/.test(rollNo)) {
        numericValues.push(Number(rollNo));
    }

    const exactConditions = ROLL_FIELD_ALIASES.flatMap(function (field) {
        const stringExact = Array.from(stringValues).map(function (value) {
            return { [field]: value };
        });

        const numericExact = numericValues.map(function (value) {
            return { [field]: value };
        });

        return stringExact.concat(numericExact);
    });

    const regexConditions = canonicalRollNo
        ? ROLL_FIELD_ALIASES.map(function (field) {
            return {
                [field]: {
                    $regex: `^${escapeRegex(canonicalRollNo)}$`,
                    $options: "i"
                }
            };
        })
        : [];

    return {
        $or: exactConditions.concat(regexConditions)
    };
}

async function readResultDataset(rollNoValue) {
    const rollNo = String(rollNoValue || "").trim();
    if (!rollNo) {
        return { students: [] };
    }

    const filter = buildRollSearchFilter(rollNo);

    const collection = await getMongoCollection();
    const rows = await collection.find(filter).toArray();

    return normalizeResultData({
        students: rows.map(function (row) {
            return normalizeMongoStudentDocument(row);
        })
    });
}

function matchParentName(inputName, recordName) {
    const input = normalizeText(inputName);
    if (!input) {
        return false;
    }

    const record = normalizeText(recordName);
    if (!record) {
        return false;
    }

    if (input.length >= 4) {
        return record.includes(input);
    }

    return record.startsWith(input);
}

function isParentNameMismatchMessage(message) {
    const lowered = normalizeText(message);
    return (
        lowered.includes("parent name does not match") ||
        lowered.includes("father name does not match") ||
        lowered.includes("mother name does not match")
    );
}

function isInvalidResultLookupMessage(message) {
    const lowered = normalizeText(message);
    return (
        lowered.includes("result not found") ||
        lowered.includes("no result found")
    );
}

function findResultRecord(payload, dataset) {
    const entered = extractEnteredFields(payload);
    const students = dataset.students || [];
    const rollNo = normalizeText(entered.rollNo);
    const fatherName = String(entered.fatherName || "").trim();
    const motherName = String(entered.motherName || "").trim();

    if (!entered.session) {
        return { error: "Session is required !" };
    }

    if (!entered.examCategory) {
        return { error: "Exam Category is required !" };
    }

    if (!entered.degree) {
        return { error: "Degree is required !" };
    }

    if (!entered.semester) {
        return { error: "Semester is required !" };
    }

    if (!rollNo) {
        return { error: "Roll No. is required !" };
    }

    if (!entered.fatherName && !entered.motherName) {
        return { error: "Mother Or Father Name is required !" };
    }

    if (fatherName.length > 0 && fatherName.length <= 3) {
        return { error: "Please enter at least the first 4 characters of your Father  Name!" };
    }

    if (motherName.length > 0 && motherName.length <= 3) {
        return { error: "Please enter at least the first 4 characters of your Father  Name!" };
    }

    const rollMatches = students.filter(function (item) {
        return normalizeText(item.rollNo) === rollNo;
    });

    if (rollMatches.length === 0) {
        return { error: "Result not found for this Roll No." };
    }

    const detailMatches = rollMatches.filter(function (item) {
        return (
            normalizeAcademicToken(item.session) === normalizeAcademicToken(entered.session) &&
            normalizeAcademicToken(item.examCategory) === normalizeAcademicToken(entered.examCategory) &&
            normalizeAcademicToken(item.degree) === normalizeAcademicToken(entered.degree) &&
            normalizeAcademicToken(item.semester) === normalizeAcademicToken(entered.semester)
        );
    });

    if (detailMatches.length === 0) {
        const available = rollMatches.map(function (item) {
            return `${item.session} | ${item.examCategory} | ${item.degree} | ${item.semester}`;
        }).join(" ; ");
        return {
            error: `No result found for selected Session, Exam Category, Degree, and Semester. Available for this roll: ${available}`
        };
    }

    const matchedRecord = detailMatches.find(function (record) {
        const fatherMatched = matchParentName(entered.fatherName, record.fatherName);
        const motherMatched = matchParentName(entered.motherName, record.motherName);
        return fatherMatched || motherMatched;
    });

    if (!matchedRecord) {
        return { error: "Parent name does not match record" };
    }

    return { record: matchedRecord };
}

function toSafeValue(value, fallback) {
    const output = String(value === undefined || value === null ? "" : value).trim();
    if (!output) {
        return fallback || "-";
    }
    return output;
}

function getFirstSubjectValue(subject, keys) {
    if (!subject || typeof subject !== "object") {
        return undefined;
    }

    for (const key of keys) {
        if (Object.prototype.hasOwnProperty.call(subject, key)) {
            return subject[key];
        }
    }

    return undefined;
}

function normalizeSubjectRows(subjects) {
    if (!Array.isArray(subjects)) {
        return [];
    }

    return subjects.map(function (subject) {
        const row = subject && typeof subject === "object" ? subject : {};

        return {
            title: toSafeValue(getFirstSubjectValue(row, ["title", "course_title", "courseTitle", "subject_title"]), "-"),
            code: toSafeValue(getFirstSubjectValue(row, ["code", "course_code", "courseCode", "subject_code"]), "-"),
            midterm: toSafeValue(getFirstSubjectValue(row, ["midterm", "marks_midterm", "midTerm", "marksMidterm"]), "-"),
            endterm: toSafeValue(getFirstSubjectValue(row, ["endterm", "marks_endterm", "endTerm", "marksEndterm"]), "-"),
            grade: toSafeValue(getFirstSubjectValue(row, ["grade", "result_grade", "letter_grade"]), "-")
        };
    });
}

function mergeRequestedFields(record, payload) {
    return {
        universityName: toSafeValue(record.universityName, "RAJASTHAN TECHNICAL UNIVERSITY, KOTA"),
        collegeName: toSafeValue(record.collegeName, "UNIVERSITY DEPARTMENT, RAJASTHAN TECHNICAL UNIVERSITY, KOTA"),
        examName: toSafeValue(record.examName, "B. Tech V SEM MAIN EXAM 2026 (GRADING)"),
        session: toSafeValue(payload.sessionField || payload.session || record.session, "-"),
        examCategory: toSafeValue(payload.examCategoryField || payload.examCategory || record.examCategory, "-"),
        degree: toSafeValue(payload.degreeField || payload.degree || record.degree, "-"),
        semester: toSafeValue(payload.semesterField || payload.semester || record.semester, "-"),
        rollNo: toSafeValue(record.rollNo, "-"),
        enrollmentNo: toSafeValue(record.enrollmentNo, "-"),
        studentName: toSafeValue(record.studentName, "-"),
        fatherName: toSafeValue(record.fatherName, "-"),
        motherName: toSafeValue(record.motherName, "-"),
        remarks: toSafeValue(record.remarks, "PASS"),
        subjects: normalizeSubjectRows(record.subjects)
    };
}

function sendPdfResponse(res, fileName, pdfBuffer, sourceLabel) {
    res.writeHead(200, {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="${fileName}"`,
        "Content-Length": pdfBuffer.length,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-PDF-Source": sourceLabel
    });
    res.end(pdfBuffer);
}

function generatePdfWithPdfKit(resultPayload) {
    return new Promise(function (resolve, reject) {
        const doc = new PDFDocument({ margin: 36, size: "A4" });
        const chunks = [];

        doc.on("data", function (chunk) {
            chunks.push(chunk);
        });

        doc.on("end", function () {
            resolve(Buffer.concat(chunks));
        });

        doc.on("error", function (error) {
            reject(error);
        });

        doc.fontSize(14).text(resultPayload.universityName, { align: "center" });
        doc.moveDown(0.25);
        doc.fontSize(10).text(resultPayload.collegeName, { align: "center" });
        doc.moveDown(0.25);
        doc.fontSize(11).text(resultPayload.examName, { align: "center" });
        doc.moveDown(0.75);

        const metadataRows = [
            ["Session", resultPayload.session],
            ["Exam Category", resultPayload.examCategory],
            ["Degree", resultPayload.degree],
            ["Semester", resultPayload.semester],
            ["Roll No", resultPayload.rollNo],
            ["Enrollment No", resultPayload.enrollmentNo],
            ["Student Name", resultPayload.studentName],
            ["Father Name", resultPayload.fatherName],
            ["Mother Name", resultPayload.motherName]
        ];

        doc.fontSize(10);
        for (const [label, value] of metadataRows) {
            doc.text(`${label}: ${toSafeValue(value, "-")}`);
        }

        doc.moveDown(0.6);
        doc.fontSize(11).text("Subjects", { underline: true });
        doc.moveDown(0.4);

        if (!Array.isArray(resultPayload.subjects) || resultPayload.subjects.length === 0) {
            doc.fontSize(10).text("No subject details available.");
        } else {
            resultPayload.subjects.forEach(function (subject, index) {
                if (doc.y > 760) {
                    doc.addPage();
                }

                const prefix = `${index + 1}. ${toSafeValue(subject.code, "-")} - ${toSafeValue(subject.title, "-")}`;
                doc.fontSize(10).text(prefix);
                doc.fontSize(9).text(`   Midterm: ${toSafeValue(subject.midterm, "-")}   Endterm: ${toSafeValue(subject.endterm, "-")}   Grade: ${toSafeValue(subject.grade, "-")}`);
            });
        }

        doc.moveDown(0.8);
        doc.fontSize(10).text(`Remarks: ${toSafeValue(resultPayload.remarks, "PASS")}`);
        doc.moveDown(0.4);
        doc.fontSize(8).fillColor("#666666").text("Generated via Node.js PDF fallback for cloud deployment compatibility.", { align: "right" });
        doc.end();
    });
}

async function handleResultLookup(req, res) {
    let payload;
    try {
        payload = await readRequestBody(req);
    } catch (error) {
        sendApiError(res, 400, error.message, "INVALID_REQUEST_BODY");
        return;
    }

    const entered = extractEnteredFields(payload);

    let dataset;
    try {
        dataset = await readResultDataset(entered.rollNo);
    } catch (error) {
        const message = (error && error.message) ? error.message : "Unable to fetch result data from MongoDB";
        sendApiError(res, 500, message, "DATA_SOURCE_ERROR");
        return;
    }

    const lookup = findResultRecord(payload, dataset);
    if (lookup.error) {
        let responseMessage = lookup.error;
        if (isParentNameMismatchMessage(lookup.error)) {
            responseMessage = "Please enter correct rollno (Mother/Father Name)!";
        } else if (isInvalidResultLookupMessage(lookup.error)) {
            responseMessage = "Invalid Rollno for Result !";
        }
        sendApiError(res, 404, responseMessage, "RESULT_NOT_FOUND");
        return;
    }

    const result = mergeRequestedFields(lookup.record, payload);
    sendJson(res, 200, { success: true, data: result });
}

async function handlePdfDownload(req, res) {
    let payload;
    try {
        payload = await readRequestBody(req);
    } catch (error) {
        sendApiError(res, 400, error.message, "INVALID_REQUEST_BODY");
        return;
    }

    const login = extractPdfcodeLogin(payload);
    const entered = extractEnteredFields(payload);
    const motherName = String(entered.motherName || "").trim();

    if (!entered.session) {
        sendApiError(res, 400, "Session is required !", "VALIDATION_ERROR");
        return;
    }

    if (!entered.examCategory) {
        sendApiError(res, 400, "Exam Category is required !", "VALIDATION_ERROR");
        return;
    }

    if (!entered.degree) {
        sendApiError(res, 400, "Degree is required !", "VALIDATION_ERROR");
        return;
    }

    if (!entered.semester) {
        sendApiError(res, 400, "Semester is required !", "VALIDATION_ERROR");
        return;
    }

    if (!login.rollNo) {
        sendApiError(res, 400, "Roll No. is required !", "VALIDATION_ERROR");
        return;
    }

    if (!login.fatherName && !motherName) {
        sendApiError(res, 400, "Mother Or Father Name is required !", "VALIDATION_ERROR");
        return;
    }

    if ((login.fatherName.length > 0 && login.fatherName.length <= 3) || (motherName.length > 0 && motherName.length <= 3)) {
        sendApiError(res, 400, "Please enter at least the first 4 characters of your Father  Name!", "VALIDATION_ERROR");
        return;
    }

    let lookup;
    try {
        const dataset = await readResultDataset(login.rollNo);
        lookup = findResultRecord(payload, dataset);
    } catch (error) {
        const message = (error && error.message) ? error.message : "Unable to fetch result data from MongoDB";
        sendApiError(res, 500, message, "DATA_SOURCE_ERROR");
        return;
    }

    if (lookup.error) {
        let responseMessage = lookup.error;
        if (isParentNameMismatchMessage(lookup.error)) {
            responseMessage = "Please enter correct rollno (Mother/Father Name)!";
        } else if (isInvalidResultLookupMessage(lookup.error)) {
            responseMessage = "Invalid Rollno for Result !";
        }
        sendApiError(res, 404, responseMessage, "RESULT_NOT_FOUND");
        return;
    }

    const matchedRecord = lookup.record;
    const resultPayload = mergeRequestedFields(matchedRecord, payload);
    const sanitizedRollNo = sanitizeFileName(login.rollNo);
    const fileName = sanitizedRollNo ? `${sanitizedRollNo}.pdf` : "gradesheet.pdf";

    if (PDF_ENGINE === "node") {
        try {
            const nodePdfBuffer = await generatePdfWithPdfKit(resultPayload);
            sendPdfResponse(res, fileName, nodePdfBuffer, "node-pdfkit");
        } catch (error) {
            const message = (error && error.message) ? error.message : "Unable to generate PDF";
            sendApiError(res, 500, message, "PDF_GENERATION_ERROR");
        }
        return;
    }

    let tempDir = "";
    try {
        if (!fs.existsSync(PDF_CONNECTOR_SCRIPT_PATH)) {
            throw new Error("generate_from_mock_data.py not found");
        }

        tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "rtu-test-template-"));
        const generatedPdfPath = path.join(tempDir, "gradesheet.pdf");
        const mongoJsonPath = path.join(tempDir, "mongo_students.json");

        const payloadForGenerator = normalizeResultData({
            session: matchedRecord.session || entered.session,
            examCategory: matchedRecord.examCategory || entered.examCategory,
            degree: matchedRecord.degree || entered.degree,
            semester: matchedRecord.semester || entered.semester,
            students: [matchedRecord]
        });

        fs.writeFileSync(mongoJsonPath, JSON.stringify(payloadForGenerator, null, 2), "utf-8");

        const scriptArgs = [
            PDF_CONNECTOR_SCRIPT_PATH,
            "--json",
            mongoJsonPath,
            "--roll",
            login.rollNo,
            "--father",
            login.fatherName,
            "--mother",
            motherName,
            "--session",
            entered.session,
            "--exam-category",
            entered.examCategory,
            "--degree",
            entered.degree,
            "--semester",
            entered.semester,
            "--output",
            generatedPdfPath,
            "--logo",
            DEFAULT_PDF_LOGO_PATH
        ];

        await runPythonTemplateGenerator(scriptArgs, { cwd: ROOT_DIR, windowsHide: true });

        if (!fs.existsSync(generatedPdfPath)) {
            throw new Error("Template PDF generation failed: output file not found");
        }

        const pdfBuffer = fs.readFileSync(generatedPdfPath);
        sendPdfResponse(res, fileName, pdfBuffer, "python-mongodb-connector");
    } catch (error) {
        const allowNodeFallback = PDF_ENGINE === "auto" || PDF_FALLBACK_TO_NODE;

        if (!allowNodeFallback) {
            const message = (error && error.message) ? error.message : "Unable to generate PDF";
            sendApiError(res, 500, message, "PDF_GENERATION_ERROR");
            return;
        }

        logWarn(`Python PDF generation failed, switching to Node fallback: ${(error && error.message) ? error.message : "Unknown error"}`);

        try {
            const fallbackPdfBuffer = await generatePdfWithPdfKit(resultPayload);
            sendPdfResponse(res, fileName, fallbackPdfBuffer, "node-pdfkit-fallback");
        } catch (fallbackError) {
            const message = (fallbackError && fallbackError.message)
                ? fallbackError.message
                : ((error && error.message) ? error.message : "Unable to generate PDF");
            sendApiError(res, 500, message, "PDF_GENERATION_ERROR");
        }
    } finally {
        if (tempDir) {
            try {
                fs.rmSync(tempDir, { recursive: true, force: true });
            } catch (cleanupError) {
                logWarn(`Failed to clean temporary PDF directory: ${cleanupError.message}`);
            }
        }
    }
}

function reportUnhandledRouteError(res, route, error) {
    const message = (error && error.message) ? error.message : "Unexpected server error";
    logError(`${route} failed: ${message}`);
    if (res.writableEnded || res.headersSent) {
        return;
    }
    sendApiError(res, 500, "Unexpected server error", "INTERNAL_ERROR");
}

function runRouteHandler(handlerPromise, res, routeName) {
    handlerPromise.catch(function (error) {
        reportUnhandledRouteError(res, routeName, error);
    });
}

const server = http.createServer(function (req, res) {
    const method = (req.method || "GET").toUpperCase();
    const requestUrl = req.url || "/";
    const requestPath = requestUrl.split("?")[0];
    const startedAt = Date.now();

    res.on("finish", function () {
        const elapsed = Date.now() - startedAt;
        logInfo(`${method} ${requestPath} -> ${res.statusCode} (${elapsed}ms)`);
    });

    if (method === "GET" && requestPath === "/api/health") {
        sendJson(res, 200, {
            success: true,
            status: "ok",
            uptimeSeconds: Math.floor(process.uptime())
        });
        return;
    }

    if (method === "POST" && requestPath.startsWith("/api/result-data")) {
        runRouteHandler(handleResultLookup(req, res), res, "result-data");
        return;
    }

    if (method === "POST" && requestPath.startsWith("/api/download-pdf")) {
        runRouteHandler(handlePdfDownload(req, res), res, "download-pdf");
        return;
    }

    const filePath = resolveFilePath(requestUrl);

    if (!filePath) {
        res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("403 Forbidden");
        return;
    }

    fs.stat(filePath, function (statError, stats) {
        if (statError) {
            res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
            res.end("404 Not Found");
            return;
        }

        if (stats.isDirectory()) {
            const directoryIndex = path.join(filePath, "index.html");
            fs.stat(directoryIndex, function (indexError, indexStats) {
                if (indexError || !indexStats.isFile()) {
                    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
                    res.end("404 Not Found");
                    return;
                }

                sendFile(res, directoryIndex);
            });
            return;
        }

        sendFile(res, filePath);
    });
});

let shutdownInProgress = false;

function shutdownServer(signalName) {
    if (shutdownInProgress) {
        return;
    }

    shutdownInProgress = true;
    logInfo(`Received ${signalName}. Starting graceful shutdown...`);

    const forceExitTimer = setTimeout(function () {
        logWarn("Force exiting after graceful shutdown timeout.");
        process.exit(1);
    }, 8000);
    forceExitTimer.unref();

    function finalizeShutdown() {
        closeMongoClient()
            .catch(function (error) {
                // Ignore shutdown-time errors while closing Mongo client.
                logWarn(`Mongo client close warning: ${error.message}`);
            })
            .finally(function () {
                clearTimeout(forceExitTimer);
                logInfo("Shutdown complete.");
                process.exit(0);
            });
    }

    try {
        server.close(function () {
            finalizeShutdown();
        });
    } catch (error) {
        logWarn(`Server close warning: ${error.message}`);
        finalizeShutdown();
    }
}

server.on("listening", function () {
    logInfo(`Server listening on ${HOST}:${PORT}`);
    logInfo(`Primary route available at ${ROUTE_ALIAS}`);
    logInfo(`PDF engine mode: ${PDF_ENGINE} (fallbackToNode=${PDF_FALLBACK_TO_NODE})`);
    if (cachedMongoConfig) {
        logInfo(`Mongo target: ${cachedMongoConfig.dbName}.${cachedMongoConfig.collectionName}`);
    }
});

server.on("error", function (error) {
    logError(`Server failed to start: ${error.message}`);
    process.exit(1);
});

server.requestTimeout = 30000;
server.headersTimeout = 35000;
server.keepAliveTimeout = 60000;

server.listen(PORT, HOST);
process.on("SIGINT", function () { shutdownServer("SIGINT"); });
process.on("SIGTERM", function () { shutdownServer("SIGTERM"); });
process.on("unhandledRejection", function (reason) {
    const message = reason instanceof Error ? reason.stack || reason.message : String(reason);
    logError(`Unhandled rejection: ${message}`);
});
process.on("uncaughtException", function (error) {
    logError(`Uncaught exception: ${error.stack || error.message}`);
    shutdownServer("uncaughtException");
});
