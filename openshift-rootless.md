OpenShift verhindert root-Rechte in Containern durch eine Kombination aus SecurityContextConstraints (SCCs), UID-Zuweisung, SELinux und Admission Controllern. Kurz gesagt: Selbst wenn du in einem Dockerfile USER root oder sudo benutzt, läuft der Container trotzdem nicht als root, sobald er im Cluster startet.

Hier ist der detaillierte Mechanismus:

## Wie verhindert OpenShift root-Rechte?
### SecurityContextConstraints (SCCs)

Die wichtigste Komponente.

Standard für normale Projekte ist:

restricted-v2 (OCP 4.12+)

früher restricted

Diese SCC verhindert:

runAsUser: 0 (root)

privileged: true

allowPrivilegeEscalation: true

Capabilities wie NET_ADMIN, SYS_ADMIN

HostPath-Mounts (bis auf wenige Ausnahmen)

Wenn der Pod einen Root-User anfordert, lehnt ihn der SCC-Admission-Controller ab.

#### Beispiel Fehlermeldung:

Error creating: pods "myapp" is forbidden:
unable to validate against any security context constraint:
[spec.containers[0].securityContext.runAsUser: Invalid value: 0:
must be in the ranges: [1000620000, 1000629999]]

## Dynamische User-ID-Zuweisung (Random UID)

OpenShift vergibt pro Namespace einen fest definierten UID-Bereich
(z. B. 1000650000–1000659999).

Pods müssen innerhalb dieses Ranges laufen.

Das bedeutet:

Container läuft nie als Root

USER im Container wird ignoriert, wenn root

Container muss auf Verzeichnisse write-bare Berechtigungen haben (group-writable)

Beispiel UID im Pod:

id -u
1000650000

## SELinux (enforcing) – Multi-Tenant Isolation

Jeder Pod bekommt ein eigenes SELinux Label:

system_u:system_r:container_t:s0:c123,c456


Dadurch kann ein Container nicht auf fremde Dateien oder Hosts zugreifen,
selbst wenn er theoretisch root wäre.

## Admission Controller “SecurityValidation” & “PodSecurity”

OpenShift validiert PodSpec → verhindert:

Root-User

HostNetwork

HostPID / HostIPC

Privileged Containers

Unsafe capabilities

Mit OCP 4.12+ kommt zusätzlich die Kubernetes Pod Security Standard "restricted".

## Warum erlaubt OpenShift Dockerfiles mit USER root, aber verhindert root im Cluster?

Weil die UID im Pod überschrieben wird.

Dockerfile:

FROM ubi8
USER root


Pod läuft trotzdem als:

uid=1000670000


OpenShift führt keine Container als root aus, auch wenn das Image es so vorsieht.

## Wie kann man root trotzdem erlauben?

Wenn du es willst (z. B. für CI, Tools, Operators):

Option A – Pod mit SCC „anyuid“ laufen lassen

Namespace (ServiceAccount) einer SCC zuweisen:

oc adm policy add-scc-to-user anyuid -z default -n my-namespace


Oder:

oc adm policy add-scc-to-sa anyuid default -n my-namespace


Damit darf der Container real als Root laufen.

## Kurz zusammengefasst
Mechanismus	Funktion
SCCs	verhindern root, Privileged, Capabilities
UID-Range per Namespace	erzwingt non-root User
SELinux enforcing	verhindert Breakout, auch bei Misconfig
Admission Controller	blockiert unsichere PodSpec-Werte
OpenShift macht aus Sicherheitsgründen alles rootless by default,
und nur gezielt freigeschaltete Projekte dürfen root nutzen.