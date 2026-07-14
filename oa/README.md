# OA 对接说明

本目录给出访客预约申请的 OA 流程定义。当前原型已经在网页端提供 “OA 审批” 页面；生产接入真实泛微 OA 时，后端会在 `POST /api/appointments` 成功校验后调用泛微创建流程接口，由 OA 内固定的访客申请账号发起流程。

## 接入流程

1. 小程序或网页提交 `POST /api/appointments`。
2. 预约系统生成申请单号和本地审批节点，并把申请主信息、访客清单、访问区域、停车信息推送给泛微 OA。
3. 泛微 OA 使用固定发起账号创建流程，表单字段中填充部门、接洽人、访问目的、访客明细等信息。
4. OA 流程按你们泛微里的流程配置流转；下一审批节点的接洽人会收到 OA 待办。
5. 每个节点审批后，OA 调用 `POST /api/oa/callback` 回传审批动作。
6. 预约系统根据回传结果更新申请状态；通过后在来访当天生成每名访客独立二维码 token。

未设置 `OA_MODE=weaver` 时，系统继续使用原型内置 OA 审批页面。

## 后端环境变量

最小配置示例：

```powershell
$env:OA_MODE="weaver"
$env:OA_BASE_URL="https://oa.essilor.com.cn:63808"
$env:OA_CREATE_PATH="/api/workflow/paService/doCreateRequest"
$env:OA_WORKFLOW_ID="你的访客预约流程ID"
$env:OA_CREATE_USER_ID="固定访客申请账号的OA人员ID"
$env:OA_ACCESS_TOKEN="泛微开放接口token"
$env:OA_TOKEN_HEADER="token"
$env:OA_CALLBACK_URL="https://你的VMS公网域名/api/oa/callback"
$env:OA_CALLBACK_SECRET="一段双方约定的回调密钥"
python .\server.py
```

如果 OA 使用自签或内网证书，可临时设置 `$env:OA_VERIFY_TLS="0"`；生产环境建议配置可信证书后保持校验开启。

## 字段映射

泛微表单字段通常由实施配置生成，必须把本系统字段映射到 OA 表单字段。主表字段使用 `OA_FIELD_MAP_JSON`，访客明细使用 `OA_VISITOR_FIELD_MAP_JSON` 和 `OA_VISITOR_DETAIL_TABLE`。

示例：

```powershell
$env:OA_FIELD_MAP_JSON='{
  "applicationNo": "field_application_no",
  "applicantName": "field_applicant_name",
  "applicantCompany": "field_company",
  "contactEmployeeId": "field_contact_id",
  "contactName": "field_contact_name",
  "contactDepartment": "field_department",
  "visitStartDate": "field_visit_start",
  "visitEndDate": "field_visit_end",
  "visitAreas": "field_visit_areas",
  "visitPurpose": "field_visit_purpose",
  "visitorCount": "field_visitor_count",
  "callbackUrl": "field_callback_url"
}'
$env:OA_VISITOR_DETAIL_TABLE="formtable_main_123_dt1"
$env:OA_VISITOR_FIELD_MAP_JSON='{
  "seq": "field_seq",
  "name": "field_visitor_name",
  "company": "field_visitor_company",
  "phone": "field_visitor_phone",
  "idType": "field_id_type",
  "idNumberMasked": "field_id_masked",
  "carPlate": "field_car_plate"
}'
```

默认请求体使用泛微常见的 `mainData` 字段列表和 `detailData.workflowRequestTableRecords` 明细格式。若你们 OA 接口需要对象格式，可设置：

```powershell
$env:OA_MAIN_DATA_STYLE="object"
$env:OA_DETAIL_DATA_STYLE="rows"
```

回调示例：

```json
{
  "applicationNo": "VMS202607030001",
  "oaInstanceId": "OA-XXXX",
  "nodeName": "接洽人审批",
  "approverId": "E1002",
  "approverName": "李华",
  "action": "approve",
  "opinion": "同意接待",
  "actionTime": "2026-07-03T10:00:00",
  "oaStatus": "processing"
}
```

如果设置了 `OA_CALLBACK_SECRET`，OA 回调需增加请求头：

```text
X-VMS-Callback-Secret: 你的回调密钥
```

支持的 `action`：`submit`、`approve`、`reject`、`cancel`、`archive`。其中 `submit` 只记录 OA 已提交状态，不会推进本地审批节点；`approve/reject/cancel/archive` 会更新预约状态。
