$ErrorActionPreference = "Stop"

$baseUrl = "http://127.0.0.1:8000"
$token = "anon-smoke"

Write-Host "[1/3] Create case"
$caseResp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/cases" -Headers @{"X-Anonymous-Token"=$token} -ContentType "application/json" -Body '{"title":"烟雾测试案件","region_code":"xian"}'
$caseId = $caseResp.id
Write-Host "case_id=$caseId"

Write-Host "[2/3] Create session"
$sessionResp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/cases/$caseId/sessions" -Headers @{"X-Anonymous-Token"=$token}
$sessionId = $sessionResp.id
Write-Host "session_id=$sessionId"

Write-Host "[3/3] Chat stream"
$chatBody = '{"message":"我被口头辞退了，怎么办？","client_seq":1,"attachments":[]}'
$chatResp = Invoke-WebRequest -Method Post -Uri "$baseUrl/api/v1/sessions/$sessionId/chat" -Headers @{"X-Anonymous-Token"=$token} -ContentType "application/json" -Body $chatBody
$chatResp.Content
