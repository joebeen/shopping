oc set volume deployment/einkauf \
  --add \
  --name=sqlite-data \
  --type=pvc \
  --claim-name=einkauf-sqlite \
  --mount-path=/data

