export interface ScenarioPreset {
  id: string;
  label: string;
  badge: string;
  description: string;
  customerRef: string;
  message: string;
  simulateActionFailure: boolean;
}

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: "en-order-fast",
    label: "EN Order Status (Auto-Complete)",
    badge: "FAST Tier",
    description: "Low-risk shipping inquiry with zero PII. Routes to FAST model and completes automatically.",
    customerRef: "CUST-DEMO-01",
    message: "Hi support, can you check the shipping status of order ORD-2026-8841? Thanks!",
    simulateActionFailure: false,
  },
  {
    id: "th-pii-tracking",
    label: "TH/EN Tracking + PII Redaction",
    badge: "PDPA Masking",
    description: "Thai/English code-mixed inquiry containing phone and email. Masked before LLM or PostgreSQL.",
    customerRef: "CUST-DEMO-02",
    message:
      "สวัสดีครับ เช็คสถานะพัสดุ ORD-2026-9920 ให้หน่อยครับ ติดต่อกลับ 089-000-1122 หรือ somchai.demo@example.com",
    simulateActionFailure: false,
  },
  {
    id: "th-refund-hitl",
    label: "TH Refund + Full PII (HITL Gate)",
    badge: "COMPLEX + HITL",
    description:
      "High-impact refund with synthetic Thai National ID, bank account, phone, and name. Pauses at AWAITING_APPROVAL.",
    customerRef: "CUST-DEMO-03",
    message:
      "คุณสมชาย ทดสอบ ขอคืนเงิน 4,500 บาท สำหรับคำสั่งซื้อ ORD-2026-5501 เลขบัตรประชาชน 1-1099-00000-01-9 โอนเข้าบัญชี 123-4-56789-0 โทร 081-234-5678",
    simulateActionFailure: false,
  },
  {
    id: "dlq-failure",
    label: "Simulated Downstream Failure -> DLQ",
    badge: "Retry + DLQ",
    description:
      "Simulates external API failure. Retries 3x with exponential backoff and moves payload safely to Dead-Letter Queue.",
    customerRef: "CUST-DEMO-05",
    message: "Please check invoice status for INV-2026-3310 and notify ops@example.com.",
    simulateActionFailure: true,
  },
];
