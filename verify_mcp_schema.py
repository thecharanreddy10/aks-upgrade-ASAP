import json
import urllib.request

url = 'https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp'
body = json.dumps({"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}).encode('utf-8')
req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=60) as resp:
    payload = json.loads(resp.read().decode('utf-8'))
print(json.dumps(payload, indent=2, sort_keys=True)[:12000])
