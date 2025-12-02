# Binary Build anlegen
oc new-build --name=einkauf --binary --strategy=docker

# Build starten und lokalen Code verwenden
oc start-build einkauf --from-dir=. --follow

