from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import ssl
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from urllib import error as urlerror, request as urlrequest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
MYSQL_SCHEMA_FILE = ROOT / "mysql_schema.sql"
DATA_FILE = ROOT / "data" / "vms-store.json"


def load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

STATUS_REVIEWING = "审批中"
STATUS_REJECTED = "已驳回"
STATUS_CANCELLED = "已取消"
STATUS_APPROVED = "已通过"
STATUS_WAIT_VISIT = "待来访"
STATUS_WAIT_CHECKIN = "待入厂"
STATUS_PART_CHECKIN = "部分入厂"
STATUS_CHECKED_IN = "已入厂"
STATUS_PART_CHECKOUT = "部分离厂"
STATUS_CHECKED_OUT = "已离厂"
STATUS_EXPIRED = "已过期"

QR_NOT_GENERATED = "未生成"
QR_READY = "待入厂"
QR_CHECKED_IN = "已入厂"
QR_INVALID = "已失效"
QR_EXPIRED = "已过期"
QR_CANCELLED = "已取消"

VISIT_NOTICE_ITEMS = [
    "已知晓工厂为重点防火单位，严禁携带易燃、易爆、易致毒等危险品进入厂区。",
    "已知晓入厂后需在门卫室完成访客登记，全程由工厂接洽人统一陪同。",
    "已知晓未经工厂书面许可，不得对厂区内设备、生产工艺、产品、原材料等拍照或录像。",
    "已知晓进入车间参观需严格遵守着装规范。",
    "已知晓参观需按既定时间和路线进行，不私自进入未授权区域。",
    "已知晓仅提前报备的车辆可驶入厂区。",
    "已知晓工厂保留因特殊情况取消参观活动的权利。",
]

NDA_ITEMS_EXTERNAL = [
    "本次访问过程中接触到的所有非公开信息均为保密信息。",
    "仅为本次访问目的使用保密信息，不向任何第三方披露或传播。",
    "未经书面许可，不对样品、原型进行分析、逆向工程、改造或拆卸。",
    "如发生保密信息丢失或未经授权披露，将第一时间通知披露方。",
    "知晓本保密承诺受中华人民共和国法律管辖。",
    "已完整阅读并理解单方保密义务协议全部条款。",
]

NDA_ITEMS_INTERNAL = [
    "已知晓集团内部资料、工艺、产品和现场信息仅限本次工作目的使用。",
    "未经许可不拍照、录像、外传或发布现场信息。",
    "访问期间遵守工厂安全、保密和陪同管理要求。",
]

EMPLOYEES = [
    {
        "id": "E1001",
        "name": "张敏",
        "department": "人事部",
        "phone": "13800001001",
        "email": "min.zhang@example.com",
        "managerId": "M2001",
        "managerName": "王强",
    },
    {
        "id": "E1002",
        "name": "李华",
        "department": "生产部",
        "phone": "13800001002",
        "email": "hua.li@example.com",
        "managerId": "M2002",
        "managerName": "赵颖",
    },
    {
        "id": "E1003",
        "name": "陈杰",
        "department": "安全部",
        "phone": "13800001003",
        "email": "jie.chen@example.com",
        "managerId": "M2003",
        "managerName": "孙磊",
    },
    {
        "id": "E1004",
        "name": "周宁",
        "department": "进出口运输部",
        "phone": "13800001004",
        "email": "ning.zhou@example.com",
        "managerId": "M2004",
        "managerName": "刘芳",
    },
]

SPECIAL_APPROVERS = {
    "车间": {"id": "S3001", "name": "车间负责人", "node": "特殊区域审批"},
    "生产": {"id": "S3001", "name": "车间负责人", "node": "特殊区域审批"},
    "安全": {"id": "S3002", "name": "安全部审批人", "node": "安全敏感区域审批"},
    "进出口": {"id": "S3003", "name": "进出口运输负责人", "node": "进出口运输审批"},
    "仓储": {"id": "S3004", "name": "仓储负责人", "node": "仓储区域审批"},
}

MENU_DEFS = [
    {"id": "overview", "title": "总体概览"},
    {"id": "oa", "title": "OA 审批"},
    {"id": "guard", "title": "门卫核验"},
    {"id": "admin", "title": "管理报表"},
    {"id": "users", "title": "账号创建"},
    {"id": "permissions", "title": "菜单分配权限"},
]
ADMIN_MENUS = [item["id"] for item in MENU_DEFS]
GUARD_MENUS = ["overview", "oa", "guard", "admin"]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def today() -> date:
    return date.today()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def is_business_day(value: date) -> bool:
    return value.weekday() < 5


def add_business_days(start: date, days: int) -> date:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if is_business_day(current):
            added += 1
    return current


def mask_id_number(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    if len(value) <= 8:
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    return value[:3] + "*" * (len(value) - 7) + value[-4:]


def hash_id_number(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(value: str) -> str:
    return hashlib.sha256(("vms-password:" + value).encode("utf-8")).hexdigest()


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12].upper()


def json_response(handler: BaseHTTPRequestHandler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type,X-VMS-Callback-Secret")
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler: BaseHTTPRequestHandler, message: str, status=400, details=None):
    payload = {"success": False, "message": message}
    if details:
        payload["details"] = details
    json_response(handler, payload, status)


def read_json_body(handler: BaseHTTPRequestHandler):
    length = int(handler.headers.get("Content-Length") or "0")
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    if not raw:
        return {}
    return json.loads(raw)


class OaIntegrationError(Exception):
    pass


def env_bool(name: str, default=False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_json(name: str, default):
    raw = os.environ.get(name)
    if not raw:
        return deepcopy(default)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OaIntegrationError(f"{name} 不是合法 JSON：{exc}") from exc
    if not isinstance(parsed, type(default)):
        raise OaIntegrationError(f"{name} 类型不正确")
    return parsed


def oa_enabled() -> bool:
    return os.environ.get("OA_MODE", "mock").strip().lower() in {"weaver", "ecology", "real"}


def format_oa_value(value):
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def mapped_fields(values: dict, field_map: dict) -> dict:
    mapped = {}
    for key, oa_field in field_map.items():
        if not oa_field:
            continue
        mapped[oa_field] = format_oa_value(values.get(key, ""))
    return mapped


def field_list(values: dict) -> list:
    return [{"fieldName": key, "fieldValue": value} for key, value in values.items()]


def build_oa_payload(appt):
    workflow_id = os.environ.get("OA_WORKFLOW_ID", "").strip()
    creator_id = os.environ.get("OA_CREATE_USER_ID", "").strip()
    if not workflow_id:
        raise OaIntegrationError("缺少 OA_WORKFLOW_ID")
    if not creator_id:
        raise OaIntegrationError("缺少 OA_CREATE_USER_ID")

    default_main_map = {
        "applicationNo": "applicationNo",
        "visitorType": "visitorType",
        "applicantName": "applicantName",
        "applicantCompany": "applicantCompany",
        "applicantPhone": "applicantPhone",
        "applicantEmail": "applicantEmail",
        "contactEmployeeId": "contactEmployeeId",
        "contactName": "contactName",
        "contactDepartment": "contactDepartment",
        "contactPhone": "contactPhone",
        "contactEmail": "contactEmail",
        "visitStartDate": "visitStartDate",
        "visitEndDate": "visitEndDate",
        "visitTimeSlot": "visitTimeSlot",
        "visitAreas": "visitAreas",
        "visitPurpose": "visitPurpose",
        "needParking": "needParking",
        "carPlate": "carPlate",
        "carVisitorName": "carVisitorName",
        "specialRequest": "specialRequest",
        "visitorCount": "visitorCount",
        "callbackUrl": "callbackUrl",
    }
    default_visitor_map = {
        "seq": "seq",
        "name": "visitorName",
        "company": "visitorCompany",
        "phone": "visitorPhone",
        "title": "visitorTitle",
        "idType": "idType",
        "idNumberMasked": "idNumberMasked",
        "idLast4": "idLast4",
        "carPlate": "carPlate",
    }
    main_map = env_json("OA_FIELD_MAP_JSON", default_main_map)
    visitor_map = env_json("OA_VISITOR_FIELD_MAP_JSON", default_visitor_map)
    callback_url = os.environ.get("OA_CALLBACK_URL", "").strip()
    main_values = deepcopy(appt)
    main_values["visitorCount"] = len(appt.get("visitors", []))
    main_values["callbackUrl"] = callback_url

    main_data = mapped_fields(main_values, main_map)
    visitor_rows = [mapped_fields(visitor, visitor_map) for visitor in appt.get("visitors", [])]
    main_style = os.environ.get("OA_MAIN_DATA_STYLE", "field_list").strip().lower()
    detail_style = os.environ.get("OA_DETAIL_DATA_STYLE", "workflow_request").strip().lower()
    table_name = os.environ.get("OA_VISITOR_DETAIL_TABLE", "").strip()

    payload = {
        "workflowId": workflow_id,
        "requestName": os.environ.get("OA_REQUEST_NAME_PREFIX", "访客预约申请") + "-" + appt["applicationNo"],
        "requestLevel": os.environ.get("OA_REQUEST_LEVEL", "0"),
        "creatorId": creator_id,
        "userId": creator_id,
        "user_id": creator_id,
    }
    payload["mainData"] = main_data if main_style == "object" else field_list(main_data)

    if table_name and visitor_rows:
        if detail_style == "rows":
            payload["detailData"] = [{"tableDBName": table_name, "datas": visitor_rows}]
        else:
            payload["detailData"] = [
                {
                    "tableDBName": table_name,
                    "workflowRequestTableRecords": [
                        {
                            "recordOrder": index,
                            "workflowRequestTableFields": field_list(row),
                        }
                        for index, row in enumerate(visitor_rows)
                    ],
                }
            ]
    return payload


def oa_headers():
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("OA_ACCESS_TOKEN", "").strip()
    if token:
        headers[os.environ.get("OA_TOKEN_HEADER", "token")] = token
    auth_header = os.environ.get("OA_AUTH_HEADER", "").strip()
    if auth_header:
        headers["Authorization"] = auth_header
    headers.update(env_json("OA_EXTRA_HEADERS_JSON", {}))
    return headers


def extract_nested_value(payload, names):
    if isinstance(payload, dict):
        for name in names:
            if name in payload and payload[name]:
                return str(payload[name])
        for value in payload.values():
            found = extract_nested_value(value, names)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = extract_nested_value(item, names)
            if found:
                return found
    return ""


def submit_appointment_to_oa(appt):
    if not oa_enabled():
        appt["oaSyncStatus"] = "mock"
        return

    payload = build_oa_payload(appt)
    appt["oaRequestPayload"] = payload if env_bool("OA_STORE_REQUEST_PAYLOAD", False) else {}
    if env_bool("OA_DRY_RUN", False):
        appt["oaSyncStatus"] = "dry_run"
        appt["oaSubmittedAt"] = now_iso()
        return

    base_url = os.environ.get("OA_BASE_URL", "https://oa.essilor.com.cn:63808").rstrip("/")
    create_path = os.environ.get("OA_CREATE_PATH", "/api/workflow/paService/doCreateRequest")
    url = base_url + "/" + create_path.lstrip("/")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(url, data=body, headers=oa_headers(), method="POST")
    context = None if env_bool("OA_VERIFY_TLS", True) else ssl._create_unverified_context()
    try:
        with urlrequest.urlopen(req, timeout=float(os.environ.get("OA_TIMEOUT_SECONDS", "15")), context=context) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OaIntegrationError(f"OA HTTP {exc.code}: {detail[:500]}") from exc
    except Exception as exc:
        raise OaIntegrationError(str(exc)) from exc

    try:
        result = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        result = {"raw": raw}
    if isinstance(result, dict):
        code = str(result.get("code", result.get("status", ""))).lower()
        success = result.get("success")
        if success is False or code in {"fail", "failed", "error", "-1"}:
            raise OaIntegrationError(json.dumps(result, ensure_ascii=False)[:500])
    oa_instance_id = extract_nested_value(result, {"requestid", "requestId", "workflowRequestId", "id"})
    if oa_instance_id:
        appt["oaInstanceId"] = oa_instance_id
    form_template = os.environ.get("OA_FORM_URL_TEMPLATE", "").strip()
    if form_template:
        appt["oaFormUrl"] = form_template.format(
            oaBaseUrl=base_url,
            oaInstanceId=appt.get("oaInstanceId", ""),
            applicationNo=appt["applicationNo"],
        )
    else:
        appt["oaFormUrl"] = base_url
    appt["oaSyncStatus"] = "sent"
    appt["oaSubmittedAt"] = now_iso()
    appt["oaLastError"] = ""


def verify_oa_callback_secret(handler: BaseHTTPRequestHandler, payload: dict) -> bool:
    secret = os.environ.get("OA_CALLBACK_SECRET", "")
    if not secret:
        return True
    provided = handler.headers.get("X-VMS-Callback-Secret", "") or payload.get("callbackSecret", "")
    return hmac.compare_digest(provided, secret)


def align_current_node_from_callback(appt, node_name: str):
    if not node_name:
        return
    current_index = appt.get("currentNodeIndex", 0)
    nodes = appt.get("approvalNodes", [])
    for index in range(current_index, len(nodes)):
        if nodes[index].get("nodeName") == node_name:
            appt["currentNodeIndex"] = index
            return


def record_oa_submit_callback(appt, payload, store):
    appt["oaStatus"] = payload.get("oaStatus", "submitted")
    if payload.get("oaInstanceId"):
        appt["oaInstanceId"] = payload["oaInstanceId"]
    appt["approvalRecords"].append(
        {
            "nodeName": payload.get("nodeName", "流程提交"),
            "approverId": payload.get("approverId", ""),
            "approverName": payload.get("approverName", ""),
            "action": "submit",
            "opinion": payload.get("opinion", ""),
            "actionTime": payload.get("actionTime") or now_iso(),
        }
    )
    appt["updatedAt"] = now_iso()
    log_operation(store, "oa_submit_callback", appt["applicationNo"], payload.get("approverName", ""), {"oaStatus": appt.get("oaStatus", "")})
    save_store(store)


def default_store():
    visit_day = today().isoformat()
    sample_token = "QR-" + short_hash("sample-" + visit_day)
    return {
        "sequenceDate": today().strftime("%Y%m%d"),
        "sequence": 1,
        "employees": deepcopy(EMPLOYEES),
        "users": default_users(),
        "appointments": [
            {
                "applicationNo": "VMS" + today().strftime("%Y%m%d") + "0001",
                "visitorType": "集团外",
                "applicantName": "样例申请人",
                "applicantCompany": "外部合作单位",
                "applicantPhone": "13900000001",
                "applicantEmail": "guest@example.com",
                "contactEmployeeId": "E1002",
                "contactName": "李华",
                "contactDepartment": "生产部",
                "contactPhone": "13800001002",
                "contactEmail": "hua.li@example.com",
                "applyDate": (today() - timedelta(days=5)).isoformat(),
                "visitStartDate": visit_day,
                "visitEndDate": visit_day,
                "visitTimeSlot": "全天",
                "visitAreas": ["办公区", "车间"],
                "visitPurpose": "供应商技术交流与车间参观",
                "needParking": True,
                "carPlate": "沪A12345",
                "carVisitorName": "王访客",
                "specialRequest": "需要会议室",
                "oaInstanceId": "OA-" + short_hash("sample-oa"),
                "oaFormUrl": "/web/#oa",
                "status": STATUS_WAIT_CHECKIN,
                "approvedAt": now_iso(),
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
                "currentNodeIndex": 3,
                "approvalNodes": [
                    {"nodeName": "接洽人审批", "approverId": "E1002", "approverName": "李华"},
                    {"nodeName": "特殊区域审批", "approverId": "S3001", "approverName": "车间负责人"},
                    {"nodeName": "部门经理审批", "approverId": "M2002", "approverName": "赵颖"},
                    {"nodeName": "流程归档", "approverId": "SYSTEM", "approverName": "系统"},
                ],
                "approvalRecords": [
                    {"nodeName": "接洽人审批", "approverId": "E1002", "approverName": "李华", "action": "approve", "opinion": "属实，同意接待", "actionTime": now_iso()},
                    {"nodeName": "特殊区域审批", "approverId": "S3001", "approverName": "车间负责人", "action": "approve", "opinion": "同意进入指定车间路线", "actionTime": now_iso()},
                    {"nodeName": "部门经理审批", "approverId": "M2002", "approverName": "赵颖", "action": "approve", "opinion": "同意", "actionTime": now_iso()},
                    {"nodeName": "流程归档", "approverId": "SYSTEM", "approverName": "系统", "action": "archive", "opinion": "审批通过并归档", "actionTime": now_iso()},
                ],
                "agreementConfirms": [],
                "visitors": [
                    {
                        "id": "VIS-" + short_hash("sample-visitor"),
                        "seq": 1,
                        "name": "王访客",
                        "company": "外部合作单位",
                        "phone": "13900000002",
                        "title": "技术经理",
                        "idType": "身份证",
                        "idNumberMasked": "310***********1234",
                        "idNumberHash": hash_id_number("310000199001011234"),
                        "idLast4": "1234",
                        "carPlate": "沪A12345",
                        "qrToken": sample_token,
                        "qrPayload": "VMS:" + sample_token,
                        "qrStatus": QR_READY,
                        "checkinTime": "",
                        "checkoutTime": "",
                        "guardCheckinUser": "",
                        "guardCheckoutUser": "",
                        "gateCode": "",
                    }
                ],
                "logs": [],
            }
        ],
        "operationLogs": [],
    }


def default_users():
    created = now_iso()
    return [
        {
            "username": "admin",
            "displayName": "管理员",
            "role": "admin",
            "passwordHash": hash_password("admin"),
            "permissions": ADMIN_MENUS,
            "createdAt": created,
            "updatedAt": created,
        },
        {
            "username": "guard01",
            "displayName": "保安1号",
            "role": "guard",
            "passwordHash": hash_password("admin"),
            "permissions": GUARD_MENUS,
            "createdAt": created,
            "updatedAt": created,
        },
    ]


def mysql_connect():
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("MySQL 存储需要安装依赖：pip install -r requirements.txt") from exc
    return pymysql.connect(
        host=os.environ.get("VMS_MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("VMS_MYSQL_PORT", "3306")),
        user=os.environ.get("VMS_MYSQL_USER", "vms_user"),
        password=os.environ.get("VMS_MYSQL_PASSWORD", ""),
        database=os.environ.get("VMS_MYSQL_DATABASE", "vms"),
        charset=os.environ.get("VMS_MYSQL_CHARSET", "utf8mb4"),
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def db_json(value):
    return json.dumps(value or [], ensure_ascii=False)


def parse_db_json(value, default):
    if value in (None, ""):
        return deepcopy(default)
    return json.loads(value)


def ensure_mysql_schema(conn):
    ddl = MYSQL_SCHEMA_FILE.read_text(encoding="utf-8")
    cursor = conn.cursor()
    for statement in ddl.split(";"):
        if statement.strip():
            cursor.execute(statement)
    conn.commit()


def load_store_mysql():
    conn = mysql_connect()
    try:
        ensure_mysql_schema(conn)
        cursor = conn.cursor()
        store = {"sequenceDate": today().strftime("%Y%m%d"), "sequence": 0, "employees": [], "users": [], "appointments": [], "operationLogs": []}
        cursor.execute("SELECT `key`, `value` FROM vms_meta")
        for row in cursor.fetchall():
            meta_key, meta_value = row["key"], row["value"]
            if meta_key == "sequenceDate":
                store["sequenceDate"] = meta_value
            elif meta_key == "sequence":
                store["sequence"] = int(meta_value)
        cursor.execute("SELECT id, name, department, phone, email, manager_id, manager_name FROM vms_employee ORDER BY id")
        for row in cursor.fetchall():
            store["employees"].append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "department": row["department"],
                    "phone": row["phone"],
                    "email": row["email"],
                    "managerId": row["manager_id"],
                    "managerName": row["manager_name"],
                }
            )
        cursor.execute("SELECT username, display_name, role, password_hash, permissions_json, created_at, updated_at FROM vms_user ORDER BY username")
        for row in cursor.fetchall():
            store["users"].append(
                {
                    "username": row["username"],
                    "displayName": row["display_name"],
                    "role": row["role"],
                    "passwordHash": row["password_hash"],
                    "permissions": parse_db_json(row["permissions_json"], []),
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"],
                }
            )
        cursor.execute("SELECT * FROM vms_appointment ORDER BY created_at DESC")
        for row in cursor.fetchall():
            appt = {
                "applicationNo": row["application_no"],
                "visitorType": row["visitor_type"],
                "applicantName": row["applicant_name"],
                "applicantCompany": row["applicant_company"],
                "applicantPhone": row["applicant_phone"],
                "applicantEmail": row["applicant_email"] or "",
                "contactEmployeeId": row["contact_employee_id"],
                "contactName": row["contact_name"],
                "contactDepartment": row["contact_department"],
                "contactPhone": row["contact_phone"],
                "contactEmail": row["contact_email"],
                "applyDate": row["apply_date"],
                "visitStartDate": row["visit_start_date"],
                "visitEndDate": row["visit_end_date"],
                "visitTimeSlot": row["visit_time_slot"],
                "visitAreas": parse_db_json(row["visit_areas_json"], []),
                "visitPurpose": row["visit_purpose"],
                "needParking": bool(row["need_parking"]),
                "carPlate": row["car_plate"] or "",
                "carVisitorName": row["car_visitor_name"] or "",
                "specialRequest": row["special_request"] or "",
                "oaInstanceId": row["oa_instance_id"] or "",
                "oaFormUrl": row["oa_form_url"] or "",
                "status": row["status"],
                "approvedAt": row["approved_at"] or "",
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "currentNodeIndex": int(row["current_node_index"] or 0),
                "approvalNodes": parse_db_json(row["approval_nodes_json"], []),
                "approvalRecords": [],
                "agreementConfirms": [],
                "visitors": [],
                "logs": parse_db_json(row["logs_json"], []),
                "oaSyncStatus": row["oa_sync_status"] or "",
                "oaSubmittedAt": row["oa_submitted_at"] or "",
                "oaLastError": row["oa_last_error"] or "",
                "oaStatus": row["oa_status"] or "",
            }
            store["appointments"].append(appt)
        by_no = {item["applicationNo"]: item for item in store["appointments"]}
        cursor.execute("SELECT * FROM vms_appointment_visitor ORDER BY application_no, seq")
        for row in cursor.fetchall():
            appt = by_no.get(row["application_no"])
            if appt:
                appt["visitors"].append(
                    {
                        "id": row["visitor_id"],
                        "seq": int(row["seq"]),
                        "name": row["name"],
                        "company": row["company"],
                        "phone": row["phone"],
                        "title": row["title"] or "",
                        "idType": row["id_type"],
                        "idNumberMasked": row["id_number_masked"],
                        "idNumberHash": row["id_number_hash"],
                        "idLast4": row["id_last4"],
                        "carPlate": row["car_plate"] or "",
                        "qrToken": row["qr_token"] or "",
                        "qrPayload": row["qr_payload"] or "",
                        "qrStatus": row["qr_status"],
                        "checkinTime": row["checkin_time"] or "",
                        "checkoutTime": row["checkout_time"] or "",
                        "guardCheckinUser": row["guard_checkin_user"] or "",
                        "guardCheckoutUser": row["guard_checkout_user"] or "",
                        "gateCode": row["gate_code"] or "",
                    }
                )
        cursor.execute("SELECT * FROM vms_approval_record ORDER BY id")
        for row in cursor.fetchall():
            appt = by_no.get(row["application_no"])
            if appt:
                appt["approvalRecords"].append(
                    {
                        "nodeName": row["node_name"],
                        "approverId": row["approver_id"] or "",
                        "approverName": row["approver_name"] or "",
                        "action": row["action"],
                        "opinion": row["opinion"] or "",
                        "actionTime": row["action_time"],
                    }
                )
        cursor.execute("SELECT * FROM vms_agreement_confirm ORDER BY id")
        for row in cursor.fetchall():
            appt = by_no.get(row["application_no"])
            if appt:
                appt["agreementConfirms"].append(
                    {
                        "agreementType": row["agreement_type"],
                        "itemCode": row["item_code"],
                        "itemContent": row["item_content"],
                        "confirmed": bool(row["confirmed"]),
                        "confirmedAt": row["confirmed_at"],
                    }
                )
        cursor.execute("SELECT action, application_no, `user`, detail_json, `time` FROM vms_operation_log ORDER BY id")
        for row in cursor.fetchall():
            store["operationLogs"].append(
                {
                    "action": row["action"],
                    "applicationNo": row["application_no"] or "",
                    "user": row["user"] or "",
                    "detail": parse_db_json(row["detail_json"], {}),
                    "time": row["time"],
                }
            )
        if not store["employees"] and not store["appointments"]:
            store = default_store()
            save_store_mysql(store)
        elif not store.get("users"):
            store["users"] = default_users()
            save_store_mysql(store)
        return store
    finally:
        conn.close()


def save_store_mysql(store):
    conn = mysql_connect()
    try:
        ensure_mysql_schema(conn)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vms_operation_log")
        cursor.execute("DELETE FROM vms_agreement_confirm")
        cursor.execute("DELETE FROM vms_approval_record")
        cursor.execute("DELETE FROM vms_appointment_visitor")
        cursor.execute("DELETE FROM vms_appointment")
        cursor.execute("DELETE FROM vms_user")
        cursor.execute("DELETE FROM vms_employee")
        cursor.execute("DELETE FROM vms_meta")
        cursor.execute("INSERT INTO vms_meta(`key`, `value`) VALUES (%s, %s)", ("sequenceDate", store.get("sequenceDate", "")))
        cursor.execute("INSERT INTO vms_meta(`key`, `value`) VALUES (%s, %s)", ("sequence", str(store.get("sequence", 0))))
        for e in store.get("employees", []):
            cursor.execute(
                "INSERT INTO vms_employee(id, name, department, phone, email, manager_id, manager_name) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (e.get("id"), e.get("name"), e.get("department"), e.get("phone"), e.get("email"), e.get("managerId"), e.get("managerName")),
            )
        for user in store.get("users", []):
            cursor.execute(
                "INSERT INTO vms_user(username, display_name, role, password_hash, permissions_json, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    user.get("username"),
                    user.get("displayName"),
                    user.get("role"),
                    user.get("passwordHash"),
                    db_json(user.get("permissions")),
                    user.get("createdAt"),
                    user.get("updatedAt"),
                ),
            )
        for appt in store.get("appointments", []):
            cursor.execute(
                """
                INSERT INTO vms_appointment(
                  application_no, visitor_type, applicant_name, applicant_company, applicant_phone, applicant_email,
                  contact_employee_id, contact_name, contact_department, contact_phone, contact_email,
                  apply_date, visit_start_date, visit_end_date, visit_time_slot, visit_areas_json, visit_purpose,
                  need_parking, car_plate, car_visitor_name, special_request, oa_instance_id, oa_form_url, status,
                  approved_at, created_at, updated_at, current_node_index, approval_nodes_json, logs_json,
                  oa_sync_status, oa_submitted_at, oa_last_error, oa_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (appt.get("applicationNo"), appt.get("visitorType"), appt.get("applicantName"), appt.get("applicantCompany"),
                appt.get("applicantPhone"), appt.get("applicantEmail"), appt.get("contactEmployeeId"), appt.get("contactName"),
                appt.get("contactDepartment"), appt.get("contactPhone"), appt.get("contactEmail"), appt.get("applyDate"),
                appt.get("visitStartDate"), appt.get("visitEndDate"), appt.get("visitTimeSlot"), db_json(appt.get("visitAreas")),
                appt.get("visitPurpose"), 1 if appt.get("needParking") else 0, appt.get("carPlate"), appt.get("carVisitorName"),
                appt.get("specialRequest"), appt.get("oaInstanceId"), appt.get("oaFormUrl"), appt.get("status"), appt.get("approvedAt"),
                appt.get("createdAt"), appt.get("updatedAt"), int(appt.get("currentNodeIndex", 0)), db_json(appt.get("approvalNodes")),
                db_json(appt.get("logs")), appt.get("oaSyncStatus", ""), appt.get("oaSubmittedAt", ""), appt.get("oaLastError", ""),
                appt.get("oaStatus", "")),
            )
            for visitor in appt.get("visitors", []):
                cursor.execute(
                    """
                    INSERT INTO vms_appointment_visitor(
                      visitor_id, application_no, seq, name, company, phone, title, id_type,
                      id_number_masked, id_number_hash, id_last4, car_plate, qr_token, qr_payload,
                      qr_status, checkin_time, checkout_time, guard_checkin_user, guard_checkout_user, gate_code
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (visitor.get("id"), appt.get("applicationNo"), int(visitor.get("seq", 0)), visitor.get("name"), visitor.get("company"),
                    visitor.get("phone"), visitor.get("title"), visitor.get("idType"), visitor.get("idNumberMasked"),
                    visitor.get("idNumberHash"), visitor.get("idLast4"), visitor.get("carPlate"), visitor.get("qrToken"),
                    visitor.get("qrPayload"), visitor.get("qrStatus"), visitor.get("checkinTime"), visitor.get("checkoutTime"),
                    visitor.get("guardCheckinUser"), visitor.get("guardCheckoutUser"), visitor.get("gateCode")),
                )
            for record in appt.get("approvalRecords", []):
                cursor.execute(
                    "INSERT INTO vms_approval_record(application_no, node_name, approver_id, approver_name, action, opinion, action_time) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (appt.get("applicationNo"), record.get("nodeName"), record.get("approverId"), record.get("approverName"),
                    record.get("action"), record.get("opinion"), record.get("actionTime")),
                )
            for confirm in appt.get("agreementConfirms", []):
                cursor.execute(
                    "INSERT INTO vms_agreement_confirm(application_no, agreement_type, item_code, item_content, confirmed, confirmed_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (appt.get("applicationNo"), confirm.get("agreementType"), confirm.get("itemCode"), confirm.get("itemContent"),
                    1 if confirm.get("confirmed") else 0, confirm.get("confirmedAt")),
                )
        for log in store.get("operationLogs", []):
            cursor.execute(
                "INSERT INTO vms_operation_log(action, application_no, `user`, detail_json, `time`) VALUES (%s, %s, %s, %s, %s)",
                (log.get("action"), log.get("applicationNo"), log.get("user"), json.dumps(log.get("detail", {}), ensure_ascii=False), log.get("time")),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_store():
    if os.environ.get("VMS_STORAGE", "mysql").strip().lower() == "json":
        if not DATA_FILE.exists():
            store = default_store()
            save_store_json(store)
            return store
        with DATA_FILE.open("r", encoding="utf-8") as handle:
            store = json.load(handle)
        if not store.get("users"):
            store["users"] = default_users()
            save_store_json(store)
        return store
    return load_store_mysql()


def save_store(store):
    if os.environ.get("VMS_STORAGE", "mysql").strip().lower() == "json":
        save_store_json(store)
        return
    save_store_mysql(store)


def save_store_json(store):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2)


def log_operation(store, action: str, application_no="", user="", detail=None):
    store.setdefault("operationLogs", []).append(
        {
            "action": action,
            "applicationNo": application_no,
            "user": user,
            "detail": detail or {},
            "time": now_iso(),
        }
    )


def next_application_no(store) -> str:
    current = today().strftime("%Y%m%d")
    if store.get("sequenceDate") != current:
        store["sequenceDate"] = current
        store["sequence"] = 0
    store["sequence"] += 1
    return f"VMS{current}{store['sequence']:04d}"


def find_appointment(store, application_no: str):
    for item in store.get("appointments", []):
        if item["applicationNo"] == application_no:
            return item
    return None


def find_visitor_by_token(store, token: str):
    if not token:
        return None, None
    for appt in store.get("appointments", []):
        for visitor in appt.get("visitors", []):
            if visitor.get("qrToken") == token or visitor.get("qrPayload") == token:
                return appt, visitor
    return None, None


def public_user(user):
    clone = deepcopy(user)
    clone.pop("passwordHash", None)
    return clone


def find_user(store, username: str):
    username = (username or "").strip()
    for user in store.get("users", []):
        if user.get("username") == username:
            return user
    return None


def get_employee(store, employee_id: str):
    for item in store.get("employees", []):
        if item["id"] == employee_id:
            return item
    return None


def is_internal_visitor_type(value: str) -> bool:
    return value in {"集团内", "依视路陆逊梯卡集团"}


def manual_contact_employee(payload):
    name = (payload.get("contactName") or "").strip()
    phone = (payload.get("contactPhone") or "").strip()
    return {
        "id": (payload.get("contactEmployeeId") or "MANUAL-CONTACT").strip() or "MANUAL-CONTACT",
        "name": name,
        "department": (payload.get("contactDepartment") or "手动填写").strip() or "手动填写",
        "phone": phone,
        "email": (payload.get("contactEmail") or "").strip(),
        "managerId": (payload.get("contactManagerId") or "MANUAL-MANAGER").strip() or "MANUAL-MANAGER",
        "managerName": (payload.get("contactManagerName") or "部门经理").strip() or "部门经理",
    }


def build_approval_nodes(employee, visit_areas):
    nodes = [
        {
            "nodeName": "接洽人审批",
            "approverId": employee["id"],
            "approverName": employee["name"],
        }
    ]
    area_text = ",".join(visit_areas or [])
    added = set()
    for keyword, approver in SPECIAL_APPROVERS.items():
        if keyword in area_text and approver["node"] not in added:
            nodes.append(
                {
                    "nodeName": approver["node"],
                    "approverId": approver["id"],
                    "approverName": approver["name"],
                }
            )
            added.add(approver["node"])
    nodes.append(
        {
            "nodeName": "部门经理审批",
            "approverId": employee["managerId"],
            "approverName": employee["managerName"],
        }
    )
    nodes.append({"nodeName": "流程归档", "approverId": "SYSTEM", "approverName": "系统"})
    return nodes


def public_appointment(appt, include_sensitive=False):
    clone = deepcopy(appt)
    for visitor in clone.get("visitors", []):
        visitor.pop("idNumberHash", None)
        if not include_sensitive:
            visitor.pop("idLast4", None)
    return clone


def can_generate_qr(appt):
    if appt.get("status") in {STATUS_CANCELLED, STATUS_REJECTED, STATUS_EXPIRED}:
        return False, "预约状态不可生成二维码"
    if appt.get("status") not in {STATUS_APPROVED, STATUS_WAIT_VISIT, STATUS_WAIT_CHECKIN, STATUS_PART_CHECKIN, STATUS_CHECKED_IN, STATUS_PART_CHECKOUT}:
        return False, "预约尚未审批通过"
    current = today()
    if not (parse_date(appt["visitStartDate"]) <= current <= parse_date(appt["visitEndDate"])):
        return False, "非来访当天，二维码暂不可用"
    return True, ""


def refresh_appointment_status(appt):
    if appt.get("status") in {STATUS_REJECTED, STATUS_CANCELLED, STATUS_EXPIRED}:
        return appt["status"]
    if appt.get("status") == STATUS_REVIEWING:
        return STATUS_REVIEWING
    visitors = appt.get("visitors", [])
    if not visitors:
        return appt.get("status", STATUS_APPROVED)
    qr_statuses = [v.get("qrStatus", QR_NOT_GENERATED) for v in visitors]
    if all(s == QR_INVALID for s in qr_statuses):
        appt["status"] = STATUS_CHECKED_OUT
    elif any(s == QR_INVALID for s in qr_statuses):
        appt["status"] = STATUS_PART_CHECKOUT
    elif all(s == QR_CHECKED_IN for s in qr_statuses):
        appt["status"] = STATUS_CHECKED_IN
    elif any(s == QR_CHECKED_IN for s in qr_statuses):
        appt["status"] = STATUS_PART_CHECKIN
    elif any(s == QR_READY for s in qr_statuses):
        appt["status"] = STATUS_WAIT_CHECKIN
    elif appt.get("approvedAt"):
        if today() < parse_date(appt["visitStartDate"]):
            appt["status"] = STATUS_WAIT_VISIT
        elif today() > parse_date(appt["visitEndDate"]):
            appt["status"] = STATUS_EXPIRED
        else:
            appt["status"] = STATUS_WAIT_CHECKIN
    return appt["status"]


def validate_appointment_payload(payload, store):
    errors = []
    required = [
        "visitorType",
        "applicantName",
        "applicantCompany",
        "applicantPhone",
        "visitStartDate",
        "visitEndDate",
        "visitTimeSlot",
        "visitAreas",
        "visitPurpose",
        "visitors",
        "visitNoticeConfirmed",
        "ndaConfirmed",
    ]
    for field in required:
        if payload.get(field) in (None, "", []):
            errors.append(f"{field} 不能为空")
    phone = payload.get("applicantPhone", "")
    if phone and not re.match(r"^\+?\d{8,15}$", phone):
        errors.append("申请人手机号格式不正确")
    email = payload.get("applicantEmail", "")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("申请人邮箱格式不正确")
    visitors = payload.get("visitors") or []
    if not 1 <= len(visitors) <= 20:
        errors.append("访客人数必须在 1 到 20 人之间")
    for index, visitor in enumerate(visitors, start=1):
        for field in ["name", "company", "phone", "idType", "idNumber"]:
            if not visitor.get(field):
                errors.append(f"第 {index} 位访客 {field} 不能为空")
        if visitor.get("phone") and not re.match(r"^\+?\d{8,15}$", visitor["phone"]):
            errors.append(f"第 {index} 位访客手机号格式不正确")
    if payload.get("needParking") and not payload.get("carPlate"):
        errors.append("需要停车位时必须填写车牌号")
    employee = get_employee(store, payload.get("contactEmployeeId", ""))
    if not employee:
        if not payload.get("contactName"):
            errors.append("接洽人不能为空")
        if not payload.get("contactPhone"):
            errors.append("接洽人手机号不能为空")
        employee = manual_contact_employee(payload)
    try:
        start = parse_date(payload.get("visitStartDate", ""))
        end = parse_date(payload.get("visitEndDate", ""))
        if start < today():
            errors.append("访问开始日期不可为过去日期")
        if end < start:
            errors.append("访问结束日期不可早于开始日期")
    except Exception:
        errors.append("访问日期格式必须为 YYYY-MM-DD")
    if len(payload.get("visitNoticeConfirmed") or []) != len(VISIT_NOTICE_ITEMS):
        errors.append("必须完整勾选工厂参观须知")
    expected_nda_count = len(NDA_ITEMS_INTERNAL if is_internal_visitor_type(payload.get("visitorType", "")) else NDA_ITEMS_EXTERNAL)
    if len(payload.get("ndaConfirmed") or []) != expected_nda_count:
        errors.append("必须完整勾选保密协议")
    return errors, employee


def create_appointment(payload, store):
    errors, employee = validate_appointment_payload(payload, store)
    if errors:
        return None, errors
    application_no = next_application_no(store)
    oa_id = "OA-" + short_hash(application_no + now_iso())
    nodes = build_approval_nodes(employee, payload.get("visitAreas", []))
    visitors = []
    for index, item in enumerate(payload["visitors"], start=1):
        id_number = item["idNumber"]
        visitors.append(
            {
                "id": "VIS-" + short_hash(application_no + str(index) + item["name"]),
                "seq": index,
                "name": item["name"],
                "company": item["company"],
                "phone": item["phone"],
                "title": item.get("title", ""),
                "idType": item["idType"],
                "idNumberMasked": mask_id_number(id_number),
                "idNumberHash": hash_id_number(id_number),
                "idLast4": id_number[-4:],
                "carPlate": item.get("carPlate") or payload.get("carPlate", ""),
                "qrToken": "",
                "qrPayload": "",
                "qrStatus": QR_NOT_GENERATED,
                "checkinTime": "",
                "checkoutTime": "",
                "guardCheckinUser": "",
                "guardCheckoutUser": "",
                "gateCode": "",
            }
        )
    confirms = []
    for index, text in enumerate(VISIT_NOTICE_ITEMS, start=1):
        confirms.append({"agreementType": "参观须知", "itemCode": f"NOTICE-{index}", "itemContent": text, "confirmed": True, "confirmedAt": now_iso()})
    nda_items = NDA_ITEMS_INTERNAL if is_internal_visitor_type(payload["visitorType"]) else NDA_ITEMS_EXTERNAL
    for index, text in enumerate(nda_items, start=1):
        confirms.append({"agreementType": "保密协议", "itemCode": f"NDA-{index}", "itemContent": text, "confirmed": True, "confirmedAt": now_iso()})
    appt = {
        "applicationNo": application_no,
        "visitorType": payload["visitorType"],
        "applicantName": payload["applicantName"],
        "applicantCompany": payload["applicantCompany"],
        "applicantPhone": payload["applicantPhone"],
        "applicantEmail": payload.get("applicantEmail", ""),
        "contactEmployeeId": employee["id"],
        "contactName": employee["name"],
        "contactDepartment": employee["department"],
        "contactPhone": employee["phone"],
        "contactEmail": employee["email"],
        "applyDate": today().isoformat(),
        "visitStartDate": payload["visitStartDate"],
        "visitEndDate": payload["visitEndDate"],
        "visitTimeSlot": payload["visitTimeSlot"],
        "visitAreas": payload["visitAreas"],
        "visitPurpose": payload["visitPurpose"],
        "needParking": bool(payload.get("needParking")),
        "carPlate": payload.get("carPlate", ""),
        "carVisitorName": payload.get("carVisitorName", ""),
        "specialRequest": payload.get("specialRequest", ""),
        "oaInstanceId": oa_id,
        "oaFormUrl": "/web/#oa",
        "oaSyncStatus": "mock",
        "oaStatus": "created",
        "oaSubmittedAt": "",
        "oaLastError": "",
        "status": STATUS_REVIEWING,
        "approvedAt": "",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "currentNodeIndex": 0,
        "approvalNodes": nodes,
        "approvalRecords": [],
        "agreementConfirms": confirms,
        "visitors": visitors,
        "logs": [],
    }
    try:
        submit_appointment_to_oa(appt)
    except OaIntegrationError as exc:
        appt["oaSyncStatus"] = "failed"
        appt["oaLastError"] = str(exc)
        return None, [f"OA 流程创建失败：{exc}"]
    store["appointments"].append(appt)
    log_operation(
        store,
        "create_appointment",
        application_no,
        payload["applicantName"],
        {"oaInstanceId": appt["oaInstanceId"], "oaSyncStatus": appt.get("oaSyncStatus", "")},
    )
    save_store(store)
    return appt, None


def approve_or_reject(appt, payload, store):
    action = payload.get("action")
    if action not in {"approve", "reject", "cancel"}:
        return False, "action 必须为 approve / reject / cancel"
    if appt.get("status") != STATUS_REVIEWING and action in {"approve", "reject"}:
        return False, "当前预约不在审批中"
    if action == "cancel":
        appt["status"] = STATUS_CANCELLED
        for visitor in appt.get("visitors", []):
            visitor["qrStatus"] = QR_CANCELLED
        node = {"nodeName": "取消", "approverId": payload.get("approverId", ""), "approverName": payload.get("approverName", "")}
    else:
        node = appt["approvalNodes"][appt.get("currentNodeIndex", 0)]
    if action == "reject" and not payload.get("opinion"):
        return False, "驳回必须填写意见"
    appt["approvalRecords"].append(
        {
            "nodeName": node["nodeName"],
            "approverId": payload.get("approverId") or node["approverId"],
            "approverName": payload.get("approverName") or node["approverName"],
            "action": action,
            "opinion": payload.get("opinion", ""),
            "actionTime": payload.get("actionTime") or now_iso(),
        }
    )
    if action == "reject":
        appt["status"] = STATUS_REJECTED
    elif action == "approve":
        appt["currentNodeIndex"] = appt.get("currentNodeIndex", 0) + 1
        next_node = appt["approvalNodes"][appt["currentNodeIndex"]]
        if next_node["nodeName"] == "流程归档":
            appt["approvalRecords"].append(
                {
                    "nodeName": "流程归档",
                    "approverId": "SYSTEM",
                    "approverName": "系统",
                    "action": "archive",
                    "opinion": "审批通过并归档",
                    "actionTime": now_iso(),
                }
            )
            appt["approvedAt"] = now_iso()
            appt["status"] = STATUS_APPROVED
            refresh_appointment_status(appt)
    appt["updatedAt"] = now_iso()
    log_operation(store, "oa_" + action, appt["applicationNo"], payload.get("approverName", ""), {"opinion": payload.get("opinion", "")})
    save_store(store)
    return True, ""


def ensure_qr_for_visitor(appt, visitor):
    ok, message = can_generate_qr(appt)
    if not ok:
        return False, message
    if visitor.get("qrStatus") in {QR_INVALID, QR_EXPIRED, QR_CANCELLED}:
        return False, "二维码已失效"
    if not visitor.get("qrToken"):
        token = "QR-" + secrets.token_urlsafe(18)
        visitor["qrToken"] = token
        visitor["qrPayload"] = "VMS:" + token
    visitor["qrStatus"] = QR_READY if not visitor.get("checkinTime") else QR_CHECKED_IN
    refresh_appointment_status(appt)
    return True, ""


def verify_token(appt, visitor, scene):
    if not appt or not visitor:
        return False, "未查询到预约", []
    status = visitor.get("qrStatus")
    if status == QR_INVALID:
        return False, "该访客已离厂，二维码已失效", []
    if status == QR_CANCELLED:
        return False, "预约已取消，二维码不可使用", []
    if status == QR_EXPIRED:
        return False, "预约已过期，请联系接洽人重新申请", []
    ok, message = can_generate_qr(appt)
    if not ok:
        return False, message, []
    if scene == "checkin":
        if status == QR_CHECKED_IN:
            return False, "该访客已入厂，不得重复登记", ["checkout"]
        if status != QR_READY:
            return False, "二维码当前不可入厂", []
        return True, "可入厂", ["checkin"]
    if scene == "checkout":
        if status == QR_READY:
            return False, "未找到入厂记录，无法离厂登记", ["checkin"]
        if status == QR_INVALID:
            return False, "该访客已离厂，二维码已失效", []
        if status == QR_CHECKED_IN:
            return True, "可离厂", ["checkout"]
    return False, "scanScene 必须为 checkin 或 checkout", []


def format_datetime(value: str) -> str:
    return (value or "").replace("T", " ")


def action_label(action: str) -> str:
    labels = {
        "create_appointment": "创建预约",
        "oa_approve": "OA审批同意",
        "oa_reject": "OA审批驳回",
        "oa_cancel": "取消预约",
        "oa_submit_callback": "OA提交流程回传",
        "oa_approve_callback": "OA审批通过回传",
        "oa_reject_callback": "OA审批驳回回传",
        "get_qr": "获取二维码",
        "guard_verify": "门卫核验",
        "guard_checkin": "确认入厂",
        "guard_checkout": "确认离厂",
        "guard_rollback_checkin": "回退入厂",
        "guard_rollback_checkout": "回退离厂",
        "export_csv": "导出CSV",
        "create_user": "创建账号",
        "update_permissions": "分配菜单权限",
    }
    return labels.get(action, action or "")


def matches_visit_date(appt, query_date: str) -> bool:
    if not query_date:
        return True
    return appt.get("visitStartDate", "") <= query_date <= appt.get("visitEndDate", "")


def list_appointments(store, query):
    items = []
    q = (query.get("q") or [""])[0].strip()
    status = (query.get("status") or [""])[0].strip()
    phone = (query.get("phone") or [""])[0].strip()
    query_date = (query.get("date") or [""])[0].strip()
    contact_name = (query.get("contactName") or query.get("name") or [""])[0].strip().lower()
    visitor_company = (query.get("visitorCompany") or query.get("company") or [""])[0].strip().lower()
    for appt in store.get("appointments", []):
        refresh_appointment_status(appt)
        if status and appt.get("status") != status:
            continue
        if phone and appt.get("applicantPhone") != phone:
            continue
        if query_date and not matches_visit_date(appt, query_date):
            continue
        visitor_companies = " ".join(v.get("company", "") for v in appt.get("visitors", []))
        if contact_name and contact_name not in appt.get("contactName", "").lower():
            continue
        if visitor_company and visitor_company not in (appt.get("applicantCompany", "") + " " + visitor_companies).lower():
            continue
        if q:
            haystack = " ".join(
                [
                    appt.get("applicationNo", ""),
                    appt.get("applicantName", ""),
                    appt.get("applicantCompany", ""),
                    appt.get("contactName", ""),
                    appt.get("contactDepartment", ""),
                    ",".join(appt.get("visitAreas", [])),
                    " ".join(v.get("name", "") + " " + v.get("phone", "") + " " + v.get("idLast4", "") + " " + v.get("carPlate", "") for v in appt.get("visitors", [])),
                ]
            )
            if q.lower() not in haystack.lower():
                continue
        items.append(public_appointment(appt))
    return items


def export_csv(store, query):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["申请单号", "访客姓名", "访客公司", "访客手机号", "访客状态", "证件类型", "脱敏证件号", "接洽人", "接洽部门", "访问区域", "访问目的", "预约访问时间", "审批状态", "入厂时间", "离厂时间", "门岗", "操作保安"])
    for appt in list_appointments(store, query):
        for visitor in appt.get("visitors", []):
            writer.writerow(
                [
                    appt["applicationNo"],
                    visitor["name"],
                    visitor["company"],
                    visitor["phone"],
                    visitor.get("qrStatus", ""),
                    visitor["idType"],
                    visitor["idNumberMasked"],
                    appt["contactName"],
                    appt["contactDepartment"],
                    "、".join(appt["visitAreas"]),
                    appt["visitPurpose"],
                    f"{appt['visitStartDate']} 至 {appt['visitEndDate']} {appt['visitTimeSlot']}",
                    appt["status"],
                    format_datetime(visitor.get("checkinTime", "")),
                    format_datetime(visitor.get("checkoutTime", "")),
                    visitor.get("gateCode", ""),
                    visitor.get("guardCheckinUser") or visitor.get("guardCheckoutUser", ""),
                ]
            )
    return "\ufeff" + output.getvalue()


class VmsHandler(BaseHTTPRequestHandler):
    server_version = "VMSPrototype/1.0"

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        if path.startswith("/api/"):
            self.handle_api_get(path, query)
            return
        self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/"):
            self.handle_api_post(path)
            return
        error_response(self, "Not Found", 404)

    def serve_static(self, path):
        if path == "/web/":
            file_path = ROOT / "web" / "index.html"
        elif path.startswith("/web/"):
            file_path = ROOT / path.lstrip("/")
        elif path.startswith("/miniprogram/") or path.startswith("/oa/"):
            file_path = ROOT / path.lstrip("/")
        else:
            error_response(self, "Not Found", 404)
            return
        try:
            resolved = file_path.resolve()
            if not str(resolved).startswith(str(ROOT)):
                error_response(self, "Forbidden", 403)
                return
            if not resolved.exists() or not resolved.is_file():
                error_response(self, "Not Found", 404)
                return
            body = resolved.read_bytes()
            content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            if resolved.suffix in {".html", ".css", ".js", ".json", ".wxml", ".wxss"}:
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            error_response(self, str(exc), 500)

    def handle_api_get(self, path, query):
        store = load_store()
        if path == "/api/config":
            json_response(
                self,
                {
                    "success": True,
                    "employees": store.get("employees", []),
                    "visitNoticeItems": VISIT_NOTICE_ITEMS,
                    "ndaItemsExternal": NDA_ITEMS_EXTERNAL,
                    "ndaItemsInternal": NDA_ITEMS_INTERNAL,
                    "today": today().isoformat(),
                    "minVisitDate": today().isoformat(),
                    "oaMode": "weaver" if oa_enabled() else "mock",
                    "menus": MENU_DEFS,
                    "statuses": [
                        STATUS_REVIEWING,
                        STATUS_REJECTED,
                        STATUS_CANCELLED,
                        STATUS_APPROVED,
                        STATUS_WAIT_VISIT,
                        STATUS_WAIT_CHECKIN,
                        STATUS_PART_CHECKIN,
                        STATUS_CHECKED_IN,
                        STATUS_PART_CHECKOUT,
                        STATUS_CHECKED_OUT,
                        STATUS_EXPIRED,
                    ],
                },
            )
            return
        if path == "/api/users":
            json_response(self, {"success": True, "items": [public_user(user) for user in store.get("users", [])]})
            return
        if path == "/api/appointments":
            json_response(self, {"success": True, "items": list_appointments(store, query)})
            return
        match = re.match(r"^/api/appointments/([^/]+)$", path)
        if match:
            appt = find_appointment(store, match.group(1))
            if not appt:
                error_response(self, "未找到申请单", 404)
                return
            refresh_appointment_status(appt)
            save_store(store)
            json_response(self, {"success": True, "item": public_appointment(appt)})
            return
        match = re.match(r"^/api/appointments/([^/]+)/visitors/([^/]+)/qr$", path)
        if match:
            appt = find_appointment(store, match.group(1))
            if not appt:
                error_response(self, "未找到申请单", 404)
                return
            visitor = next((v for v in appt.get("visitors", []) if v["id"] == match.group(2)), None)
            if not visitor:
                error_response(self, "未找到访客", 404)
                return
            ok, message = ensure_qr_for_visitor(appt, visitor)
            if not ok:
                error_response(self, message, 400)
                return
            appt["updatedAt"] = now_iso()
            log_operation(store, "get_qr", appt["applicationNo"], "", {"visitor": visitor["name"]})
            save_store(store)
            json_response(self, {"success": True, "visitor": public_appointment({"visitors": [visitor]})["visitors"][0]})
            return
        if path == "/api/oa/tasks":
            items = []
            for appt in store.get("appointments", []):
                if appt.get("status") == STATUS_REVIEWING:
                    node = appt["approvalNodes"][appt.get("currentNodeIndex", 0)]
                    public = public_appointment(appt, include_sensitive=True)
                    public["currentNode"] = node
                    items.append(public)
            json_response(self, {"success": True, "items": items})
            return
        if path == "/api/guard/today":
            items = []
            q = (query.get("q") or [""])[0].strip().lower()
            query_date = (query.get("date") or [today().isoformat()])[0].strip() or today().isoformat()
            name = (query.get("name") or [""])[0].strip().lower()
            company = (query.get("company") or [""])[0].strip().lower()
            for appt in store.get("appointments", []):
                if not matches_visit_date(appt, query_date):
                    continue
                if appt.get("status") in {STATUS_REJECTED, STATUS_CANCELLED}:
                    continue
                if not appt.get("approvedAt"):
                    continue
                if query_date == today().isoformat():
                    for visitor in appt.get("visitors", []):
                        ensure_qr_for_visitor(appt, visitor)
                refresh_appointment_status(appt)
                public = public_appointment(appt, include_sensitive=True)
                if name:
                    names = " ".join([public.get("applicantName", "")] + [v.get("name", "") for v in public.get("visitors", [])]).lower()
                    if name not in names:
                        continue
                if company:
                    companies = " ".join([public.get("applicantCompany", "")] + [v.get("company", "") for v in public.get("visitors", [])]).lower()
                    if company not in companies:
                        continue
                if q:
                    haystack = " ".join(
                        [
                            public.get("applicantName", ""),
                            public.get("applicantCompany", ""),
                            " ".join(v.get("name", "") + " " + v.get("company", "") for v in public.get("visitors", [])),
                        ]
                    )
                    if q not in haystack.lower():
                        continue
                items.append(public)
            save_store(store)
            json_response(self, {"success": True, "items": items})
            return
        if path == "/api/admin/export":
            csv_text = export_csv(store, query)
            body = csv_text.encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=vms-export.csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            log_operation(store, "export_csv", "", query.get("user", ["admin"])[0], {"query": query})
            save_store(store)
            return
        if path == "/api/admin/logs":
            logs = list(reversed(store.get("operationLogs", [])))
            page = max(int((query.get("page") or ["1"])[0] or "1"), 1)
            page_size = int((query.get("pageSize") or ["20"])[0] or "20")
            if page_size not in {20, 50, 100, 500}:
                page_size = 20
            start = (page - 1) * page_size
            items = []
            for item in logs[start : start + page_size]:
                public = deepcopy(item)
                public["time"] = format_datetime(public.get("time", ""))
                public["actionLabel"] = action_label(public.get("action", ""))
                items.append(public)
            json_response(self, {"success": True, "items": items, "total": len(logs), "page": page, "pageSize": page_size})
            return
        error_response(self, "Not Found", 404)

    def handle_api_post(self, path):
        store = load_store()
        try:
            payload = read_json_body(self)
        except Exception as exc:
            error_response(self, "JSON 解析失败", 400, str(exc))
            return
        if path == "/api/auth/login":
            username = (payload.get("username") or "").strip()
            password = payload.get("password") or ""
            user = find_user(store, username)
            if not user or user.get("passwordHash") != hash_password(password):
                error_response(self, "账号或密码错误", 401)
                return
            json_response(self, {"success": True, "user": public_user(user), "menus": MENU_DEFS})
            return
        if path == "/api/users":
            username = (payload.get("username") or "").strip()
            if not username:
                error_response(self, "账号不能为空", 400)
                return
            if find_user(store, username):
                error_response(self, "账号已存在", 400)
                return
            password = payload.get("password") or "admin"
            permissions = payload.get("permissions") or GUARD_MENUS
            user = {
                "username": username,
                "displayName": (payload.get("displayName") or username).strip(),
                "role": (payload.get("role") or "guard").strip(),
                "passwordHash": hash_password(password),
                "permissions": [item for item in permissions if item in ADMIN_MENUS],
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
            }
            store.setdefault("users", []).append(user)
            log_operation(store, "create_user", "", payload.get("operator", ""), {"username": username})
            save_store(store)
            json_response(self, {"success": True, "user": public_user(user)})
            return
        match = re.match(r"^/api/users/([^/]+)/permissions$", path)
        if match:
            username = match.group(1)
            user = find_user(store, username)
            if not user:
                error_response(self, "账号不存在", 404)
                return
            permissions = payload.get("permissions") or []
            user["permissions"] = [item for item in permissions if item in ADMIN_MENUS]
            user["updatedAt"] = now_iso()
            log_operation(store, "update_permissions", "", payload.get("operator", ""), {"username": username, "permissions": user["permissions"]})
            save_store(store)
            json_response(self, {"success": True, "user": public_user(user)})
            return
        if path == "/api/appointments":
            appt, errors = create_appointment(payload, store)
            if errors:
                error_response(self, "预约提交校验失败", 400, errors)
                return
            json_response(
                self,
                {
                    "success": True,
                    "applicationNo": appt["applicationNo"],
                    "status": appt["status"],
                    "oaInstanceId": appt["oaInstanceId"],
                    "nextAction": "等待 OA 审批",
                    "item": public_appointment(appt),
                },
                201,
            )
            return
        if path == "/api/oa/callback":
            if not verify_oa_callback_secret(self, payload):
                error_response(self, "OA 回调密钥校验失败", 401)
                return
            appt = find_appointment(store, payload.get("applicationNo", ""))
            if not appt:
                error_response(self, "未找到申请单", 404)
                return
            if payload.get("oaInstanceId"):
                appt["oaInstanceId"] = payload["oaInstanceId"]
            appt["oaStatus"] = payload.get("oaStatus", appt.get("oaStatus", ""))
            action = payload.get("action")
            if action == "submit":
                record_oa_submit_callback(appt, payload, store)
                json_response(self, {"success": True, "appointmentStatus": appt["status"], "item": public_appointment(appt)})
                return
            if action == "archive":
                has_archive = any(record.get("action") == "archive" for record in appt.get("approvalRecords", []))
                if not has_archive:
                    appt["approvalRecords"].append(
                        {
                            "nodeName": payload.get("nodeName", "流程归档"),
                            "approverId": payload.get("approverId", "SYSTEM"),
                            "approverName": payload.get("approverName", "系统"),
                            "action": "archive",
                            "opinion": payload.get("opinion", "审批通过并归档"),
                            "actionTime": payload.get("actionTime") or now_iso(),
                        }
                    )
                appt["approvedAt"] = appt.get("approvedAt") or now_iso()
                appt["status"] = STATUS_APPROVED
                appt["updatedAt"] = now_iso()
                refresh_appointment_status(appt)
                log_operation(store, "oa_archive_callback", appt["applicationNo"], payload.get("approverName", ""), {"oaStatus": appt.get("oaStatus", "")})
                save_store(store)
                json_response(self, {"success": True, "appointmentStatus": appt["status"], "item": public_appointment(appt)})
                return
            align_current_node_from_callback(appt, payload.get("nodeName", ""))
            action_map = {"approve": "approve", "reject": "reject", "cancel": "cancel"}
            callback_payload = {
                "action": action_map.get(action, action),
                "opinion": payload.get("opinion", ""),
                "approverId": payload.get("approverId", ""),
                "approverName": payload.get("approverName", ""),
                "actionTime": payload.get("actionTime", ""),
            }
            ok, message = approve_or_reject(appt, callback_payload, store)
            if not ok:
                error_response(self, message, 400)
                return
            json_response(self, {"success": True, "appointmentStatus": appt["status"], "item": public_appointment(appt)})
            return
        match = re.match(r"^/api/oa/tasks/([^/]+)/action$", path)
        if match:
            appt = find_appointment(store, match.group(1))
            if not appt:
                error_response(self, "未找到申请单", 404)
                return
            ok, message = approve_or_reject(appt, payload, store)
            if not ok:
                error_response(self, message, 400)
                return
            json_response(self, {"success": True, "appointmentStatus": appt["status"], "item": public_appointment(appt)})
            return
        match = re.match(r"^/api/appointments/([^/]+)/cancel$", path)
        if match:
            appt = find_appointment(store, match.group(1))
            if not appt:
                error_response(self, "未找到申请单", 404)
                return
            ok, message = approve_or_reject(appt, {"action": "cancel", "opinion": payload.get("opinion", "申请取消"), "approverName": payload.get("user", "")}, store)
            if not ok:
                error_response(self, message, 400)
                return
            json_response(self, {"success": True, "item": public_appointment(appt)})
            return
        if path == "/api/guard/qr/verify":
            token = payload.get("qrToken", "").replace("VMS:", "")
            appt, visitor = find_visitor_by_token(store, token)
            ok, message, actions = verify_token(appt, visitor, payload.get("scanScene", "checkin"))
            log_operation(store, "guard_verify", appt["applicationNo"] if appt else "", payload.get("guardUserId", ""), {"ok": ok, "message": message})
            save_store(store)
            json_response(
                self,
                {
                    "success": True,
                    "valid": ok,
                    "message": message,
                    "availableActions": actions,
                    "appointment": public_appointment(appt, include_sensitive=True) if appt else None,
                    "visitor": public_appointment({"visitors": [visitor]}, include_sensitive=True)["visitors"][0] if visitor else None,
                },
            )
            return
        if path == "/api/guard/checkin":
            if payload.get("scanScene") and payload.get("scanScene") != "checkin":
                error_response(self, "当前场景是离厂，不能执行确认入厂", 400)
                return
            token = payload.get("qrToken", "").replace("VMS:", "")
            appt, visitor = find_visitor_by_token(store, token)
            ok, message, _ = verify_token(appt, visitor, "checkin")
            if not ok:
                error_response(self, message, 400)
                return
            if not payload.get("idVerified"):
                error_response(self, "证件未核验通过，不允许入厂", 400)
                return
            visitor["checkinTime"] = now_iso()
            visitor["guardCheckinUser"] = payload.get("guardUserId", "")
            visitor["gateCode"] = payload.get("gateCode", "")
            visitor["qrStatus"] = QR_CHECKED_IN
            refresh_appointment_status(appt)
            appt["updatedAt"] = now_iso()
            log_operation(store, "guard_checkin", appt["applicationNo"], payload.get("guardUserId", ""), {"visitor": visitor["name"], "gateCode": visitor["gateCode"]})
            save_store(store)
            json_response(self, {"success": True, "checkinTime": visitor["checkinTime"], "visitorStatus": visitor["qrStatus"], "appointmentStatus": appt["status"], "item": public_appointment(appt)})
            return
        if path == "/api/guard/checkout":
            if payload.get("scanScene") and payload.get("scanScene") != "checkout":
                error_response(self, "当前场景是入厂，不能执行确认离厂", 400)
                return
            token = payload.get("qrToken", "").replace("VMS:", "")
            appt, visitor = find_visitor_by_token(store, token)
            ok, message, _ = verify_token(appt, visitor, "checkout")
            if not ok:
                error_response(self, message, 400)
                return
            visitor["checkoutTime"] = now_iso()
            visitor["guardCheckoutUser"] = payload.get("guardUserId", "")
            visitor["gateCode"] = payload.get("gateCode", visitor.get("gateCode", ""))
            visitor["qrStatus"] = QR_INVALID
            refresh_appointment_status(appt)
            appt["updatedAt"] = now_iso()
            log_operation(store, "guard_checkout", appt["applicationNo"], payload.get("guardUserId", ""), {"visitor": visitor["name"], "gateCode": visitor["gateCode"]})
            save_store(store)
            json_response(self, {"success": True, "checkoutTime": visitor["checkoutTime"], "qrStatus": visitor["qrStatus"], "visitorStatus": visitor["qrStatus"], "appointmentStatus": appt["status"], "item": public_appointment(appt)})
            return
        if path == "/api/guard/rollback":
            token = payload.get("qrToken", "").replace("VMS:", "")
            appt, visitor = find_visitor_by_token(store, token)
            if not appt or not visitor:
                error_response(self, "未查询到预约", 404)
                return
            action = payload.get("action")
            if action == "checkin":
                if visitor.get("qrStatus") != QR_CHECKED_IN:
                    error_response(self, "只有已入厂状态可以回退入厂操作", 400)
                    return
                visitor["checkinTime"] = ""
                visitor["guardCheckinUser"] = ""
                visitor["qrStatus"] = QR_READY
                log_operation(store, "guard_rollback_checkin", appt["applicationNo"], payload.get("guardUserId", ""), {"visitor": visitor["name"]})
            elif action == "checkout":
                if visitor.get("qrStatus") != QR_INVALID or not visitor.get("checkoutTime"):
                    error_response(self, "只有已离厂状态可以回退离厂操作", 400)
                    return
                visitor["checkoutTime"] = ""
                visitor["guardCheckoutUser"] = ""
                visitor["qrStatus"] = QR_CHECKED_IN
                log_operation(store, "guard_rollback_checkout", appt["applicationNo"], payload.get("guardUserId", ""), {"visitor": visitor["name"]})
            else:
                error_response(self, "action 必须为 checkin 或 checkout", 400)
                return
            refresh_appointment_status(appt)
            appt["updatedAt"] = now_iso()
            save_store(store)
            json_response(self, {"success": True, "visitorStatus": visitor["qrStatus"], "appointmentStatus": appt["status"], "item": public_appointment(appt)})
            return
        error_response(self, "Not Found", 404)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))


def run(port: int):
    load_store()
    server = ThreadingHTTPServer(("127.0.0.1", port), VmsHandler)
    print(f"VMS prototype running at http://127.0.0.1:{port}/web/")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    selected_port = int(os.environ.get("PORT", "18088"))
    run(selected_port)
