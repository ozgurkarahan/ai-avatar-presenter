"""Copy all blobs from sub-2 stclgsqan6efeuy/slide-images to sub-3 stam564oxavvhhk/slide-images via AAD."""
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

SRC_ACCT = "stclgsqan6efeuy"
DST_ACCT = "stam564oxavvhhk"
CONTAINER = "slide-images"

cred = DefaultAzureCredential()
src = BlobServiceClient(f"https://{SRC_ACCT}.blob.core.windows.net", credential=cred)
dst = BlobServiceClient(f"https://{DST_ACCT}.blob.core.windows.net", credential=cred)

src_c = src.get_container_client(CONTAINER)
dst_c = dst.get_container_client(CONTAINER)

names = [b.name for b in src_c.list_blobs()]
print(f"Source blobs: {len(names)}")

ok = err = 0
for i, name in enumerate(names, 1):
    try:
        src_blob = src_c.get_blob_client(name)
        data = src_blob.download_blob().readall()
        # Preserve content settings
        props = src_blob.get_blob_properties()
        from azure.storage.blob import ContentSettings
        cs = ContentSettings(
            content_type=props.content_settings.content_type,
            content_encoding=props.content_settings.content_encoding,
            content_disposition=props.content_settings.content_disposition,
            cache_control=props.content_settings.cache_control,
        )
        dst_c.upload_blob(name=name, data=data, overwrite=True, content_settings=cs)
        ok += 1
    except Exception as e:
        print(f"  ERR {name}: {e}")
        err += 1
    if i % 10 == 0 or i == len(names):
        print(f"  {i}/{len(names)} ok={ok} err={err}")

print(f"\nDONE ok={ok} err={err}")
