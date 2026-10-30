# Hardware Research

## Current decision

No hardware will be purchased and the calculator will not be opened or modified during the initial software phase.

## Questions to investigate later

- What physical interfaces are accessible on the TI-Nspire CX II?
- Which interfaces can Ndless software reliably use?
- Is bidirectional communication possible with an external device?
- What are the electrical levels, power limits, and protection requirements?
- Is there sufficient internal space, and what are the thermal and mechanical constraints?
- Can the design be made reversible and safe for the calculator?

## Important cautions

A phone hotspot only provides Wi-Fi connectivity to devices that already have compatible networking hardware and software. It does not by itself add wireless capability to the calculator.

An ESP32 or similar board would require a deliberately designed physical connection, firmware, and a calculator-side communication implementation. It should not be assumed to appear as a plug-and-play network adapter.

Any future hardware proposal must include evidence, a wiring/interface plan, power analysis, and a safe test strategy before parts are ordered or the calculator is opened.
