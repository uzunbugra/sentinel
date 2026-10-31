import { describe, expect, it } from "vitest"

import { apiSchema } from "./api-schema"
import { loadedModelResponse, mlEvidence } from "@/test/ml-fixtures"

// The handwritten types in ml.ts mirror the ML-06 backend. These checks fail
// when api-schema.ts (regenerated from FastAPI) drifts away from them.

type SchemaObject = { properties?: Record<string, unknown>; required?: string[] }
const schemas = apiSchema.components.schemas as unknown as Record<string, SchemaObject>

function fieldsOf(name: string): string[] {
  return Object.keys(schemas[name]?.properties ?? {}).sort()
}

describe("ML types match the generated OpenAPI schema", () => {
  it("ModelStatusResponse", () => {
    expect(Object.keys(loadedModelResponse).sort()).toEqual(fieldsOf("ModelStatusResponse"))
  })

  it("ActiveModel", () => {
    expect(Object.keys(loadedModelResponse.model!).sort()).toEqual(fieldsOf("ActiveModel"))
  })

  it("ModelMetrics", () => {
    expect(Object.keys(loadedModelResponse.model!.metrics!).sort()).toEqual(fieldsOf("ModelMetrics"))
  })

  it("TopFeature", () => {
    const details = mlEvidence.details as { top_features: Record<string, unknown>[] }
    expect(Object.keys(details.top_features[0]).sort()).toEqual(fieldsOf("TopFeature"))
  })

  it("load status values", () => {
    const status = schemas.ModelStatusResponse.properties?.status as { enum?: string[] }
    expect([...(status.enum ?? [])].sort()).toEqual(["invalid", "loaded", "not_loaded"])
  })
})
