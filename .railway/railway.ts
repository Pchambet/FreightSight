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
    env: { APP_DB_PASSWORD: preserve(), APP_ENV: preserve(), BACKUP_ENCRYPTION_KEY: preserve(), NEXT_PUBLIC_SENTRY_DSN: preserve(), SCW_ACCESS_KEY: preserve(), SCW_BUCKET: preserve(), SCW_DEFAULT_ORGANIZATION_ID: preserve(), SCW_DEFAULT_PROJECT_ID: preserve(), SCW_REGION: preserve(), SCW_SECRET_KEY: preserve(), SENTRY_DSN: preserve(), CLERK_AUTHORIZED_PARTIES: preserve(), CLERK_ISSUER: preserve(), CLERK_JWKS_URL: preserve(), CORS_ORIGINS: preserve(), DATABASE_URL: preserve(), DEFAULT_BASE_CURRENCY: preserve(), FX_API_URL: preserve(), MIGRATIONS_DATABASE_URL: preserve(), PYTHONDONTWRITEBYTECODE: preserve(), PYTHONUNBUFFERED: preserve(), UV_COMPILE_BYTECODE: preserve(), UV_LINK_MODE: preserve(), UV_PROJECT_ENVIRONMENT: preserve() },
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
