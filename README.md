# genset-controller

An ESPHome controller for a petrol/syngas generator in an off-grid micro-grid,
plus a browser simulator for its state machine.

The generator is a **FOGO FH9000R** (Honda GX390, 8.5 kVA, 400/230 V three-phase,
AVR on all three phases), retrofitted with an electric starter, a relay start
input and a battery. A **Deye SUN-20K-SG05LP3-EU-SM2** inverter running in island
mode asks for the generator by closing its G-start dry contact. The controller
sits between the two: it reads that contact, cranks within safe limits, and stops
the engine by shorting the ignition to ground when the request goes away.

Longer term the generator runs on **water gas** made on site. The gas comes from
a hybrid reactor that works in two phases: it first carbonises wood into a
charcoal bed, then gasifies that same bed with steam. One vessel, two operating
phases — nothing is discharged or stored in between. Charcoal is the seasonal
energy store: PV covers the day, LiFePO4 carries the night, charcoal carries
the winter.

## Files

| file | what it is |
|---|---|
| `state-machine.yaml` | the state machine as data — states, transitions, inputs, outputs, parameters. The canonical definition. |
| `genset-controller.yaml` | ESPHome configuration for a SMARTBOB SM-MINI-0808R. Implements the same machine in a 100 ms `interval` lambda. |
| `hybrid-skeleton.yaml` | state skeleton for the gasifier (`GAZ_`) and the retort (`RET_`) layers. `mode: skeleton` — no pins assigned, not flashable. For review on paper. |
| `index.html` | the simulator. Single file, loads `state-machine.yaml` inline, runs the machine in the browser with a model of the engine. PL/EN. |

## The simulator

Open `index.html` in a browser — no build step, no server. It loads js-yaml from
a CDN and nothing else.

The left panel is the state diagram with the live transition highlighted. The
four columns are the inputs (clickable, as if you were shorting terminals in the
cabinet), the outputs with their indicator lamps, the current state with its
armed transitions and their timers, and an event log that records **every pin
change on its own line**.

An engine model generates the run confirmation for you: the starter catches after
a drawn 2.0–2.8 s, one attempt in four does not catch at all, and the engine
coasts down 1.5–2.5 s after the ignition drops. Toggling the run-confirmed input
by hand takes the model offline so you can force any state you want.

Edit the machine live with the **YAML** button. Nothing in the engine recognises
a state by its name: a fault state is one carrying `fault: true`, and the engine
model watches the `starter` and `ignition` outputs rather than the state name.
That is what lets the gasifier and retort layers be added later without touching
the simulator's engine.

## Language

Configuration files are **English only** — one canonical source. The simulator
carries a Polish translation keyed **by path into the YAML structure**
(`states.AGR_READY.transitions.0.description`), not by text matching, so it
survives `{parameter}` interpolation and YAML line wrapping. A missing key falls
back to the English text, which means editing the definition in the browser never
breaks the display.

State identifiers (`AGR_READY`, …) stay English in both languages. They are
ESPHome entity names and MQTT topics; showing them translated would get in the
way of comparing the panel against the controller's own log.

## Naming convention

States carry a prefix: **`AGR_`** for the generator, **`RET_`** for the reactor's
carbonisation phase, **`GAZ_`** for its gasification phase. Without it
`AGR_RUNNING` and `GAZ_RUNNING` would collide — a running engine and a reactor
producing gas are not the same state.

`RET_` and `GAZ_` are **two phases of one vessel**, not two machines. The
carbonisation cycle ends at `RET_COOLDOWN` and what it leaves behind is the
charcoal bed the gasification phase burns, in place. The first consequence is an
interlock: the vessel cannot carbonise and gasify at once, so the two phase
groups are mutually exclusive and `RET_COLD` is the only place the phase may
change. What decides which group may run is `bed`: empty, wood, or char.

The genset is a genuinely separate machine, joined by **single signals**, not by
one transition table. `GAZ_` raises `gas_ready`, which widens the `AGR_READY`
exit condition from `gen_request` to `gen_request and gas_ready`; `AGR_` raises
`engine_drawing`, which the reactor needs because gas does not flow without the
engine drawing it. One combined table would multiply out and be unreadable at
the first bug.

## Hardware rules that are not negotiable

**The ignition relay is energise-to-run.** Energised, it holds the NC contact in
the kill line open. Loss of power, a hung controller or a broken wire closes that
contact, shorts the ignition and stops the engine. Wired the other way round, a
dead controller means a generator running unsupervised.

**The permit chain is hardwired and in series:** emergency stop (NC) + CO
detector (NC) + the controller's relay, driving a coil whose NC contact sits in
the kill line. The Deye G-start contact must **not** be put in that chain — it
would kill the run-down phase. Safety signals in hardware, request signals in
software.

**The starter goes through a one-shot 3–4 s timer relay** that will not re-trigger
until its input has dropped. A software limit does not protect against a hung
ESP32.

The controller does not drive the starter directly: `RELAY-02` energises a
contactor coil.

## External hardware required

| function | device | note |
|---|---|---|
| run confirmation (IN-02) | DIN-rail voltage monitoring relay, e.g. [Relpol RPN-.VF-A400](https://www.relpol.pl/Produkty/Przekazniki-nadzorcze/Przekazniki-nadzorcze-modulowe/Przekazniki-nadzorcze-RPN-.VF-A400) | volt-free contact on the generator phase |
| permit chain | DIN relay with a **changeover** contact | its NC sits in the kill line |
| starter limit | **one-shot** timer relay, 3–4 s | will not re-trigger without the input dropping |
| starter | contactor | the controller cannot feed the starter directly |
| CO | detector with **two** contacts | one to IN-03, one into the hardwired chain |

## Controller board

**SMARTBOB SM-MINI-0808R.** On the MINI a single MCP23017 at `0x20` serves both
the inputs and the relays (the LITE has two, at `0x20` and `0x21`). The vendor
spreadsheet gives identical mapping for board revisions 1.5, 1.6 and 1.7, so the
revision is not critical here.

```
inputs  1-8    B0/8  A6/6  A5/5  A4/4  A3/3  A2/2  A1/1  A0/0
outputs 1-8    A7/7  B1/9  B2/10 B3/11 B4/12 B5/13 B6/14 B7/15
I2C1 SDA G15 / SCL G5     RS485 TX G33 / RX G13
input reference: PLUS GPIO12 / MINUS GPIO4
```

A volt-free contact needs the inputs referenced to ground, so `on_boot` sets
IN-GND on and IN-VCC off.

> **ESPHome trap.** YAML does not allow duplicate top-level keys, and a second
> `binary_sensor:` block **silently overrides the first** — this once deleted all
> four inputs with no parse error at all. Add entities to the existing block.

## Reading the Deye over Modbus

The inverter is a Modbus RTU **slave at address 1, 9600 8N1**. The register block
in `genset-controller.yaml` is written out but commented: battery SOC `588`,
voltage `587`, power `590`, PV `672`/`673`, GEN port voltage `661` and power `667`.

Registers `661` and `667` are an independent witness against IN-02 — the same
fact, the generator's output voltage, measured a second way by a different device.

**The register addresses are community-sourced, not from Deye.** The map comes
from the SG04LP3 family; Deye does not publish a register table in the manual.
Compare the first readings against the inverter's own screen.

> **RS485 direction control.** ESPHome does not drive a DE/RE pin. On modules
> without automatic direction switching the queries go out and the reply never
> comes back — "no response received" with a perfectly healthy inverter. Turn on
> `debug: direction: BOTH`; TX with no RX means a direction problem, not wrong
> register addresses.

## Two clocks, not one

An early version gated the start on a single timer and claimed it both filtered
contact chatter and enforced a dwell in ready. It did neither reliably, because
a state timer measures **time in the state**, which has already elapsed while the
controller sat idle. Clicking the request after the controller had been ready for
an hour cranked instantly.

These are two requirements on two different clocks and they are now separate:

- **`t_request_hold`** — the request must be continuously ON for this long. It
  lives in the **input filter** (`delayed_on` on the binary sensor), because
  holding a signal is signal conditioning.
- **`t_ready`** — minimum dwell in `AGR_READY` after a closed cycle or a fault
  reset. Correctly a state timer, and correctly irrelevant once the controller
  has stood idle: a rested engine needs no dwell.

The filter is asymmetric on purpose — slow to accept, immediate to release. A
transient request must not start the engine, but a withdrawn request must stop
the cranking at once.

## Defects found by simulation

Running the machine found four real faults, all fixed in both implementations:

1. the starter kept cranking for the full attempt after the request was withdrawn
2. a cycle could begin with the engine already running
3. a fault could be cleared with the engine still running
4. the attempt counter read 2 of 3 on the way into the fault state

plus the two-clocks defect above. Equivalence between `state-machine.yaml` and
the C++ lambda is checked mechanically, transition by transition.

## Status

The simulator and both configurations are finished. The hardware is not built.
The next step is a **generator acceptance test on petrol**: wire the FH9000R into
the inverter's GEN input and confirm the Deye synchronises and charges the bank.
One afternoon, no cost, and it de-risks the whole topology.
