import { describe, expect, it } from "vitest"
import { render, screen, within } from "@testing-library/react"

import { ModelEvaluation } from "./model-evaluation"
import {
  legacyEnsembleEvidence,
  mlEvidence,
  olderModelEvidence,
  ruleEvidence,
} from "@/test/ml-fixtures"

function row(feature: string) {
  return screen.getByRole("rowheader", { name: new RegExp(feature) }).closest("tr")!
}

describe("ModelEvaluation", () => {
  it("alarm anındaki sürüm, skor, eşik ve katkıları gösterir", () => {
    render(<ModelEvaluation fraudType="ml_model" evidence={[mlEvidence]} />)

    const section = screen.getByRole("region", { name: "Model değerlendirmesi" })
    expect(section).toHaveTextContent("fraud-lgbm-20261105-a1b2c3d")
    expect(section).toHaveTextContent("fs-1")
    expect(screen.getByTestId("threshold-comparison")).toHaveTextContent(
      "Skor eşiğin üstünde (0.8123 ≥ 0.3700)",
    )
    expect(within(row("sender_unique_receivers_7d")).getByText("+2.31")).toBeInTheDocument()
    expect(within(row("sender_unique_receivers_7d")).getByText("14.00")).toBeInTheDocument()
    expect(screen.getByText("Gönderenin farklı alıcıları (7 gün)")).toBeInTheDocument()
    expect(section).toHaveTextContent(/log-odds/)
    expect(section).toHaveTextContent("Taban değer: -6.91")
  })

  it("sıfır katkıyı ve eksik değeri ayrı gösterir", () => {
    render(<ModelEvaluation fraudType="ml_model" evidence={[mlEvidence]} />)

    const zero = within(row("currency_mismatch")).getAllByRole("cell")
    expect(zero.map((c) => c.textContent)).toEqual(["0.00", "0.00"])

    const missing = within(row("sender_seconds_since_prev")).getAllByRole("cell")
    expect(missing.map((c) => c.textContent)).toEqual(["—", "-0.18"])
  })

  it("eski modelle üretilmiş alarmda kendi kaydını gösterir", () => {
    render(<ModelEvaluation fraudType="ml_model" evidence={[olderModelEvidence]} />)

    const section = screen.getByRole("region", { name: "Model değerlendirmesi" })
    expect(section).toHaveTextContent("fraud-lgbm-20261020-0000aaa")
    expect(section).not.toHaveTextContent("fraud-lgbm-20261105-a1b2c3d")
    expect(screen.getByTestId("threshold-comparison")).toHaveTextContent(
      "Skor eşiğin altında (0.4100 < 0.4500)",
    )
    expect(screen.getByText("Katkı kaydı yok.")).toBeInTheDocument()
  })

  it("skor veya eşik eksikse karşılaştırma yapmaz", () => {
    render(
      <ModelEvaluation
        fraudType="ml_model"
        evidence={[{ detector_type: "ml_model", details: { score: 0.5 } }]}
      />,
    )
    expect(screen.getByTestId("threshold-comparison")).toHaveTextContent(
      "Skor veya eşik kaydedilmemiş",
    )
    expect(screen.getByRole("region")).toHaveTextContent("Katkı birimi kaydedilmemiş.")
  })

  it("cold start bilgisini gösterir", () => {
    render(
      <ModelEvaluation
        fraudType="ml_model"
        evidence={[{ ...mlEvidence, details: { ...mlEvidence.details, history_cold_start: true } }]}
      />,
    )
    expect(screen.getByText(/cold start/)).toBeInTheDocument()
  })

  it("metadata'sız eski ML alarmında açıklama yerine durum mesajı gösterir", () => {
    render(<ModelEvaluation fraudType="ml_ensemble" evidence={[legacyEnsembleEvidence]} />)

    expect(screen.getByRole("region", { name: "Model değerlendirmesi" })).toHaveTextContent(
      "model metadata'sı kaydedilmeden önce üretildi",
    )
    expect(screen.queryByTestId("threshold-comparison")).toBeNull()
  })

  it("ML olmayan alarmda bölüm çıkmaz", () => {
    const { container } = render(
      <ModelEvaluation fraudType="mule_account" evidence={[ruleEvidence]} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
