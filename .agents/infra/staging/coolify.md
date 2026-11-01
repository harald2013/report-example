# Coolify

Reference for the Coolify instance that hosts the `staging` environment of
this repository.

A UUID is the identifier Coolify uses in its API and MCP tools.

## Instance wh-coolify

URL: http://wh-coolify:8000/

Port register: [Port blocks on wh-coolify](https://github.com/harald2013/infrastructure/blob/main/coolify/port-register.md) in the infrastructure repository

The port register lists the blocks of host and Serve ports reserved per project and service on this instance; the repository that operates the instance maintains it.

Reach this instance through MCP Jungle under the server name `coolify-wh-coolify`. Its tools are named `coolify-wh-coolify__…`.

The objects below nest. The server runs the applications. The project contains the environment. The environment contains the resources. Each resource is assigned to one destination, a Docker network that Coolify manages on one server.

```
wh-coolify
└── server localhost
    └── project report-example
        └── environment staging
            ├── postgres
            ├── temporal
            ├── temporal-ui
            ├── api
            └── worker
```

### Servers

| Name | UUID | Description |
| --- | --- | --- |
| localhost | kisymismhd6tci7xrbjb1r1y | wh-coolify, reachable at host.docker.internal |

### Destinations

The UUID identifies the destination in the Coolify API and MCP tools; it is not the Docker network ID. The destination name and the Docker network name differ. The server's default destination `coolify` belongs to project IDP and is documented in the infrastructure repository.

| Name | UUID | Server | Docker network | Description |
| --- | --- | --- | --- | --- |
| localhost-report-example-staging | ob9mjye7qpm4k1ytlvdwongd | localhost | `report-example-staging` | Own destination of this project; fixed subnet `172.30.0.0/24`; all staging resources |

### Projects

| Name | UUID | Description |
| --- | --- | --- |
| report-example | mxu2fn0yhgpp6xfooibg56ru | Portable report example, synthetic staging data |

### Environments

| Name | UUID | Description |
| --- | --- | --- |
| staging | gxgtic2h6zlchftuzyqnodhg | Independent image applications |

### Resources

| Name | UUID | Kind | Destination | Deployment | Description |
| --- | --- | --- | --- | --- | --- |
| postgres | 1gvjtntleypij9lvcfdid5yk | application | localhost-report-example-staging | Image: `postgres` | Staging postgres; network alias `report-postgres`; not exposed |
| temporal | uf0runx9tuaasz0boge5mpb2 | application | localhost-report-example-staging | Image: `temporalio/auto-setup` | Staging temporal; network alias `report-temporal`; not exposed |
| temporal-ui | ggb4ntoezlha1g7arkrkvmvy | application | localhost-report-example-staging | Image: `temporalio/ui` | Temporal UI; network alias `report-temporal-ui`; https://wh-coolify.tail8fba42.ts.net:15101/ (tailnet only); fixed address `172.30.0.12`; Tailscale Serve `15101` → `172.30.0.12:8080` |
| api | mtyncf8p2yaqsnjyg72adga6 | application | localhost-report-example-staging | Image: `ghcr.io/harald2013/report-example-api` | Staging API; network alias `report-api`; https://wh-coolify.tail8fba42.ts.net:15100/ (tailnet only); fixed address `172.30.0.13`; Tailscale Serve `15100` → `172.30.0.13:8000` |
| worker | ekvdn0bmgy3bilxcnvgamcvt | application | localhost-report-example-staging | Image: `ghcr.io/harald2013/report-example-worker` | Staging worker; network alias `report-worker`; not exposed |

## Configuration

Shared variables of the environment `staging`; the applications reference them.

| Variable | Scope | Secret | Source |
| --- | --- | --- | --- |
| APP_ENV | shared | no | Coolify shared variable |
| TEMPORAL_ADDRESS | shared | no | Coolify shared variable |
| TEMPORAL_NAMESPACE | shared | no | Coolify shared variable |
| TEMPORAL_TASK_QUEUE | shared | no | Coolify shared variable |
| TEMPORAL_TLS | shared | no | Coolify shared variable |
| POSTGRES_PASSWORD | shared | yes | Coolify shared variable; postgres `POSTGRES_PASSWORD`, temporal `POSTGRES_PWD` |
| DATABASE_URL | shared | yes | Coolify shared variable; api, worker |
| API_TOKEN | shared | yes | Coolify shared variable; api, worker |

## Project additions

PostgreSQL uses the persistent volume
`1gvjtntleypij9lvcfdid5yk-report-example-postgres-data` (storage UUID
`cgccmjqd5a0ebmcpw3fdrhnx`) at `/var/lib/postgresql/data`. PostgreSQL uses
consistent container naming and must stop before replacement.

## Application port assignments

Within the delegated TCP range `15100`–`15119` on wh-coolify's Tailnet
address, report-example uses Serve HTTPS `15100` for the API and `15101`
for Temporal UI. Other ports remain available within this delegation after
a live collision check. Internal container ports need no central reservation.
