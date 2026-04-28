"""List Apr 24 presentations from Cosmos."""
import datetime
import json
import os

from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient

cred = DefaultAzureCredential()
client = CosmosClient(
    "https://cosmos-clgsqan6efeuy.documents.azure.com:443/", credential=cred
)
db = client.get_database_client("ai-presenter")

print("containers:", [c["id"] for c in db.list_containers()])
c = db.get_container_client("presentations")

items = list(c.query_items(query="SELECT * FROM c", enable_cross_partition_query=True))
print(f"total={len(items)}")
if items:
    print("keys[0]:", list(items[0].keys()))

os.makedirs("data/clara_regen", exist_ok=True)

apr24 = []
for x in items:
    ts = x.get("_ts")
    when = datetime.datetime.utcfromtimestamp(ts) if ts else None
    if when and when.strftime("%Y-%m-%d") == "2026-04-24":
        apr24.append((when.isoformat(), x.get("id"), x.get("title") or x.get("name")))

apr24.sort()
print("apr24 count:", len(apr24))
for row in apr24:
    print(row)

# Save all apr24 items
for when, pid, title in apr24:
    item = next(x for x in items if x.get("id") == pid)
    out = f"data/clara_regen/{pid}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(item, fh, indent=2, default=str)
