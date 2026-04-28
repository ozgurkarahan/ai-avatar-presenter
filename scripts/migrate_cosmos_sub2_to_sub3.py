"""Migrate Cosmos DB ai-presenter database from sub-2 to sub-3."""
import os
from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential

SRC = "https://cosmos-clgsqan6efeuy.documents.azure.com:443/"
DST = "https://cosmos-am564oxavvhhk.documents.azure.com:443/"
DB = "ai-presenter"
CONTAINERS = [
    ("presentations", "/id"),
    ("uc1_progress", "/id"),
]

cred = DefaultAzureCredential()
src = CosmosClient(SRC, cred)
dst = CosmosClient(DST, cred)

src_db = src.get_database_client(DB)
dst_db = dst.create_database_if_not_exists(DB)

for cname, pkey in CONTAINERS:
    print(f"\n== {cname} ==")
    try:
        src_c = src_db.get_container_client(cname)
        # Probe by reading 1 item
        items = list(src_c.read_all_items(max_item_count=1))
    except Exception as e:
        print(f"  source missing/empty: {e.__class__.__name__}")
        continue
    dst_c = dst_db.create_container_if_not_exists(id=cname, partition_key=PartitionKey(path=pkey))
    n = 0
    for item in src_c.read_all_items():
        item.pop("_rid", None); item.pop("_self", None); item.pop("_etag", None); item.pop("_attachments", None); item.pop("_ts", None)
        dst_c.upsert_item(item)
        n += 1
        if n % 5 == 0:
            print(f"  copied {n}...")
    print(f"  done: {n} docs")
print("\nDONE")
