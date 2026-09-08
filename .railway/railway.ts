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
    env: { APP_DB_PASSWORD: preserve(), APP_ENV: preserve(), CLERK_AUTHORIZED_PARTIES: preserve(), CLERK_ISSUER: preserve(), CLERK_JWKS_URL: preserve(), CORS_ORIGINS: preserve(), DATABASE_URL: preserve(), DEFAULT_BASE_CURRENCY: preserve(), FX_API_URL: preserve(), MIGRATIONS_DATABASE_URL: preserve(), PYTHONDONTWRITEBYTECODE: preserve(), PYTHONUNBUFFERED: preserve(), UV_COMPILE_BYTECODE: preserve(), UV_LINK_MODE: preserve(), UV_PROJECT_ENVIRONMENT: preserve() },
  });

  return project("steadfast-balance", {
    resources: [FreightSight, PostgresEU, postgreseuVolume],
  });
});
