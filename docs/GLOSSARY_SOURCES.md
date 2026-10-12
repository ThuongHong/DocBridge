# Built-in automotive glossary sources

Reviewed on 2026-10-12. This original curated glossary contains 97 Chinese-to-English
term pairs for automotive documents, with emphasis on publicly documented Bosch
braking/sensor products and AUTOSAR Classic/Adaptive software terminology.

## Scope and provenance

The linked primary sources establish the English product, architecture and module
names. **The Chinese equivalents are editorial translations selected for this app;
this is not an official Bosch or AUTOSAR bilingual glossary.** Each term's `source_id`
points to one supporting official source. Synonymous Chinese phrases may share a
target. Entries contain short terminology only; definitions, specification text,
figures and vendor glossaries have not been reproduced.

Bosch coverage includes ABS/ESP, braking, vehicle dynamics and automotive sensors.
AUTOSAR coverage includes CP/AP, SWC, RTE, BSW, MCAL, COM, DEM, DCM, PDU/PduR,
CAN communication, supervision, memory and selected Adaptive functional clusters.
This set contains Simplified Chinese phrases. Traditional Chinese regional terms
are not generated automatically because mechanical character conversion can give
incorrect technical vocabulary.

No proprietary Bosch project names, internal abbreviations, or unpublished product
terminology are included. The spelling of a brand or standard name does not imply
that this app is endorsed, certified or supplied by its owner. ESP and AUTOSAR are
trademarks of their respective owners.

## Source coverage

The IDs below match `sources[].id` and `terms[].source_id` in
`src/converter/data/automotive_glossary.json`. AUTOSAR release numbers identify the
particular supporting reference; this set does not claim to describe every module
in the newest release.

| Source ID | Official primary reference | Entries |
| --- | --- | ---: |
| `bosch-safety` | [Bosch Mobility — Driving safety](https://www.bosch-mobility.com/en/solutions/driving-safety/) | 14 |
| `bosch-esp` | [Bosch Mobility — Electronic stability program](https://www.bosch-mobility.com/en/solutions/driving-safety/electronic-stability-program/) | 4 |
| `bosch-sensors` | [Bosch Mobility — Sensors](https://www.bosch-mobility.com/en/solutions/sensors/) | 14 |
| `bosch-by-wire` | [Bosch Mobility — Brake-by-wire](https://www.bosch-mobility.com/en/solutions/driving-safety/brake-by-wire/) | 6 |
| `autosar-cp` | [AUTOSAR — Classic Platform](https://www.autosar.org/standards/classic-platform/) | 16 |
| `autosar-vfb` | [AUTOSAR — Virtual Functional Bus, R23-11](https://www.autosar.org/fileadmin/standards/R23-11/CP/AUTOSAR_CP_EXP_VFB.pdf) | 3 |
| `autosar-j1939` | [AUTOSAR — SAE J1939 Diagnostic Communication Manager, R25-11](https://www.autosar.org/fileadmin/standards/R25-11/CP/AUTOSAR_CP_SWS_SAEJ1939DiagnosticCommunicationManager.pdf) | 11 |
| `autosar-dcm` | [AUTOSAR — Diagnostic Communication Manager, R24-11](https://www.autosar.org/fileadmin/standards/R24-11/CP/AUTOSAR_CP_SWS_DiagnosticCommunicationManager.pdf) | 2 |
| `autosar-cantp` | [AUTOSAR — CAN Transport Layer, R23-11](https://www.autosar.org/fileadmin/standards/R23-11/CP/AUTOSAR_CP_SWS_CANTransportLayer.pdf) | 3 |
| `autosar-com` | [AUTOSAR — Communication, R19-11](https://www.autosar.org/fileadmin/standards/R19-11/CP/AUTOSAR_SWS_COM.pdf) | 1 |
| `autosar-nvm` | [AUTOSAR — NVRAM Manager, R24-11](https://www.autosar.org/fileadmin/standards/R24-11/CP/AUTOSAR_CP_SWS_NVRAMManager.pdf) | 2 |
| `autosar-wdgm` | [AUTOSAR — Watchdog Manager, R24-11](https://www.autosar.org/fileadmin/standards/R24-11/CP/AUTOSAR_CP_SWS_WatchdogManager.pdf) | 4 |
| `autosar-ap-wg` | [AUTOSAR — Adaptive Platform working groups](https://www.autosar.org/working-groups/adaptive-platform) | 4 |
| `autosar-ap-design` | [AUTOSAR — Adaptive Platform Design, R20-11](https://www.autosar.org/fileadmin/standards/R20-11/AP/AUTOSAR_EXP_PlatformDesign.pdf) | 5 |
| `autosar-phm` | [AUTOSAR — Platform Health Management, R24-11](https://www.autosar.org/fileadmin/standards/R24-11/AP/AUTOSAR_AP_SWS_PlatformHealthManagement.pdf) | 5 |
| `autosar-catalog` | [AUTOSAR — Official document catalog](https://www.autosar.org/search/) | 1 |
| `autosar-cross-standard` | [AUTOSAR — Cross-Standard working groups](https://www.autosar.org/working-groups/cross-standard) | 2 |

## Integration and review notes

The JSON schema is `{version, title, sources, terms}`. Sources contain `{id, title,
url}`; terms contain `{source, target, domain, source_id}`. Keep the packaged JSON
unchanged as a read-only baseline and store user preferences/custom additions in
application storage. Load it with `importlib.resources.files("converter").joinpath(
"data", "automotive_glossary.json")` so installed wheels and frozen builds use the
same resource. PyInstaller must collect the JSON as package data.

Apply the preset only when enabled for Chinese-to-English translation. User glossary
entries should override the built-in target for the same source phrase. Prefer longer
phrases first: for example, the brake-by-wire actuator phrase contains the shorter
brake-by-wire phrase. A single replacement pass with stable placeholder tokens avoids
replacing text inserted by an earlier term. Send only matching terms in a model prompt
to avoid wasting context and imposing unrelated domain terms.

Some phrases also occur outside automotive work (for example, execution management
and time synchronization). A domain preset cannot disambiguate every sentence.
Review technical output against the project-specific terminology list, especially
when a supplier uses different names or abbreviations. This is translation assistance,
not an implementation of or a conformance claim against AUTOSAR.
