variable "REGISTRY" {
  default = "lakemind"
}

variable "VERSION" {
  default = "dev"
}

variable "OUTPUT_TYPE" {
  default = "docker"
}

target "_common" {
  platforms = ["linux/amd64"]
  output = ["type=${OUTPUT_TYPE}"]
}

target "server-api" {
  inherits   = ["_common"]
  context    = "LakeMindServer"
  dockerfile = "Dockerfile"
  tags       = ["${REGISTRY}/server-api:${VERSION}"]
}

target "postgres-age" {
  inherits   = ["_common"]
  context    = "LakeMindServer/docker/postgres-age"
  dockerfile = "Dockerfile"
  tags       = ["${REGISTRY}/postgres-age:${VERSION}"]
}

target "mcp-suite" {
  inherits   = ["_common"]
  context    = "LakeMindMCP"
  dockerfile = "Dockerfile"
  tags       = ["${REGISTRY}/mcp-suite:${VERSION}"]
}

target "model-serving" {
  inherits   = ["_common"]
  context    = "LakeMindModelServing"
  dockerfile = "Dockerfile"
  tags       = ["${REGISTRY}/model-serving:${VERSION}"]
}

target "control-center" {
  inherits   = ["_common"]
  context    = "LakeMindControlCenter"
  dockerfile = "Dockerfile"
  tags       = ["${REGISTRY}/control-center:${VERSION}"]
}

target "ray-worker" {
  inherits   = ["_common"]
  context    = "LakeMindServer/docker/ray-worker"
  dockerfile = "Dockerfile"
  tags       = ["${REGISTRY}/ray-worker:${VERSION}"]
}

group "core" {
  targets = [
    "postgres-age",
    "server-api",
    "mcp-suite",
    "model-serving",
    "control-center",
    "ray-worker"
  ]
}

group "apps" {
  targets = [
    "server-api",
    "mcp-suite",
    "model-serving",
    "control-center"
  ]
}
