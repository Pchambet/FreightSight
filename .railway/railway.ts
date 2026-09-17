import { defineRailway, github, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const PostgresEU = postgres("PostgresEU", { region: "europe-west4-drams3a" });
  PostgresEU.networking = { privateNetworkEndpoint: "postgreseu" };
  const postgreseuVolume = volume("postgreseu-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 500 });
  const FreightSight = service("FreightSight", {
    source: github("Pchambet/FreightSight", { checkSuites: false, rootDirectory: "/backend" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "/backend/Dockerfile" },
    healthcheck: "/readyz",
    healthcheckTimeout: 120,
    preDeploy: "alembic upgrade head",
    replicas: { "europe-west4-drams3a": 1 },
    networking: { privateNetworkEndpoint: "freightsight" },
    // APP_ENV is pinned, not preserved: it is the switch that closes the unauthenticated development
    // principal and turns the production guards on, so it must not live only in the dashboard.
    // The two ALLOW_* switches are pinned off for the same reason: a second lock only helps if it is versioned.
    // RESEND_API_KEY and ALERTS_FROM_EMAIL are listed before they exist so that a later apply keeps them.
    env: { APP_DB_PASSWORD: preserve(), APP_ENV: "prod", ALLOW_DEV_PRINCIPAL: "false", ALLOW_PRIVATE_OUTBOUND: "false", ALERTS_FROM_EMAIL: preserve(), RESEND_API_KEY: preserve(), BACKUP_ENCRYPTION_KEY: preserve(), NEXT_PUBLIC_SENTRY_DSN: preserve(), SCW_ACCESS_KEY: preserve(), SCW_BUCKET: preserve(), SCW_DEFAULT_ORGANIZATION_ID: preserve(), SCW_DEFAULT_PROJECT_ID: preserve(), SCW_REGION: preserve(), SCW_SECRET_KEY: preserve(), SENTRY_DSN: preserve(), SHIPSGO_API_KEY: preserve(), TERMINAL49_API_KEY: preserve(), TRACKING_WEBHOOK_SECRET_SHIPSGO: preserve(), TRACKING_WEBHOOK_SECRET_TERMINAL49: preserve(), CLERK_AUTHORIZED_PARTIES: preserve(), CLERK_ISSUER: preserve(), CLERK_JWKS_URL: preserve(), CORS_ORIGINS: preserve(), DATABASE_URL: preserve(), DEFAULT_BASE_CURRENCY: preserve(), ERP_ENCRYPTION_KEY: preserve(), FX_API_URL: preserve(), MIGRATIONS_DATABASE_URL: preserve(), PYTHONDONTWRITEBYTECODE: preserve(), PYTHONUNBUFFERED: preserve(), UV_COMPILE_BYTECODE: preserve(), UV_LINK_MODE: preserve(), UV_PROJECT_ENVIRONMENT: preserve() },
  });

  // Same image as the API, no migrations (the API's pre-deploy runs them), no public port: the
  // Procrastinate worker runs the periodic tracking and alert jobs against the same database.
  const Worker = service("worker", {
    source: github("Pchambet/FreightSight", { checkSuites: false, rootDirectory: "/backend" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "/backend/Dockerfile" },
    startCommand: "python -m app.worker",
    replicas: { "europe-west4-drams3a": 1 },
    env: {
      APP_ENV: "prod",
      DATABASE_URL: "${{FreightSight.DATABASE_URL}}",
      DEFAULT_BASE_CURRENCY: "${{FreightSight.DEFAULT_BASE_CURRENCY}}",
      FX_API_URL: "${{FreightSight.FX_API_URL}}",
      SENTRY_DSN: "${{FreightSight.SENTRY_DSN}}",
      ERP_ENCRYPTION_KEY: "${{FreightSight.ERP_ENCRYPTION_KEY}}",
      TERMINAL49_API_KEY: "${{FreightSight.TERMINAL49_API_KEY}}",
      SHIPSGO_API_KEY: "${{FreightSight.SHIPSGO_API_KEY}}",
      TRACKING_WEBHOOK_SECRET_SHIPSGO: "${{FreightSight.TRACKING_WEBHOOK_SECRET_SHIPSGO}}",
      TRACKING_WEBHOOK_SECRET_TERMINAL49: "${{FreightSight.TRACKING_WEBHOOK_SECRET_TERMINAL49}}",
      // The worker is the one that sends the alert digests: without these two it logs them instead.
      RESEND_API_KEY: "${{FreightSight.RESEND_API_KEY}}",
      ALERTS_FROM_EMAIL: "${{FreightSight.ALERTS_FROM_EMAIL}}",
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONUNBUFFERED: "1",
      UV_COMPILE_BYTECODE: "1",
      UV_LINK_MODE: "copy",
      UV_PROJECT_ENVIRONMENT: "/opt/venv",
    },
  });

  // Nightly encrypted pg_dump to Scaleway Object Storage (Paris). Dumps as the OWNER role: with the
  // application role, Row Level Security would silently drop every tenant row from the backup.
  // The secrets (SCW_*, BACKUP_ENCRYPTION_KEY) live on the FreightSight service and are referenced.
  const Backup = service("backup", {
    source: github("Pchambet/FreightSight", { checkSuites: false, rootDirectory: "/backend" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "/backend/Dockerfile" },
    startCommand: "python -m app.backup",
    cronSchedule: "0 3 * * *",
    replicas: { "europe-west4-drams3a": 1 },
    env: {
      APP_ENV: "prod",
      MIGRATIONS_DATABASE_URL: "${{FreightSight.MIGRATIONS_DATABASE_URL}}",
      BACKUP_ENCRYPTION_KEY: "${{FreightSight.BACKUP_ENCRYPTION_KEY}}",
      SCW_ACCESS_KEY: "${{FreightSight.SCW_ACCESS_KEY}}",
      SCW_SECRET_KEY: "${{FreightSight.SCW_SECRET_KEY}}",
      SCW_BUCKET: "${{FreightSight.SCW_BUCKET}}",
      SCW_REGION: "${{FreightSight.SCW_REGION}}",
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONUNBUFFERED: "1",
      UV_COMPILE_BYTECODE: "1",
      UV_LINK_MODE: "copy",
      UV_PROJECT_ENVIRONMENT: "/opt/venv",
    },
  });

  return project("steadfast-balance", {
    resources: [FreightSight, Worker, Backup, PostgresEU, postgreseuVolume],
  });
});
