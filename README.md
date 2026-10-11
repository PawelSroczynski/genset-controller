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
| `plant.yaml` | the installation around the controller: bank, PV, loads, and the Deye with its thresholds. Separate on purpose — `state-machine.yaml` is what gets flashed, this is the world it sits in. |
| `index.html` | the simulator. Single file, all three YAMLs embedded, runs the machine in the browser with models of the engine and of the plant. PL/EN. |
| `embed.py` | injects the YAML sources into `index.html`. Run it after touching any of them. |

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

## The request is not an input

`gen_request` used to be a free input you toggled by hand. It is not an input at
all: it is an **output of the Deye**, computed from battery SOC with hysteresis.
The manual is explicit — *"Start = 30%: when battery SOC or voltage drop to this
set value, the inverter will start the generator"*, and the normally-open Gen
Signal relay closes at that point. Toggling it modelled the wrong layer.

The real chain is a feedback loop:

```
cells -> BMS (SOC estimate) -> Deye (Start threshold) -> GS contact
      -> IN-01 -> GENS_ -> genset -> GEN port -> charges the bank -> cells
```

So the simulator now models the plant and the operator drives **physical
conditions** — PV, island load, the PPE3 shower — while the Deye decides and
IN-01 follows. IN-01 stays clickable: clicking it takes the Deye model offline,
the same pattern as the engine model.

**The hysteresis is the point.** Start 30 %, stop 80 %. Releasing the contact at
the start threshold would stop the genset the instant it began to help.

**Which terminal carries the start signal depends on the "Signal ISLAND MODE"
setting** — ticked it is GS, unticked GV. Island mode is on here, so GS, which
matches the G-start (1,2) pair. Confirm it on the device.

## Two clocks

A full cycle is about 19 hours: roughly 16 h draining the bank and 3 h charging.
The state machine runs in real seconds. One clock cannot serve both.

The plant clock runs at 240x while nothing is happening and drops to real time
the moment the controller has something to show — cranking, the pause, stopping,
a fault, and the request hold in `GENS_READY`. The multiplier is always on screen.
The restriction to `GENS_READY` matters: the request stays asserted through the
whole charging run, and without it the clock sat at 1x for hours of charging.

## What the genset load factor is for

The Deye caps charging at `gen_charge_a`, 40 A by default. At 51.2 V that is
about 2.05 kW, which is **less than the 3.5 kW the genset makes on water gas**.
With only the base load running, the simulator shows the genset at **73 % load** —
part-loaded, which is precisely what a gasifier does not want; it wants long runs
at full load.

The setting is left at its default on purpose. What it should be has to be
settled on the inverter, against what the cells accept through the BMS and what
the three-phase genset can give. The gauge is there to answer that with a number
rather than an opinion.

## Language

Configuration files are **English only** — one canonical source. The simulator
carries a Polish translation keyed **by path into the YAML structure**
(`states.GENS_READY.transitions.0.description`), not by text matching, so it
survives `{parameter}` interpolation and YAML line wrapping. A missing key falls
back to the English text, which means editing the definition in the browser never
breaks the display.

State identifiers (`GENS_READY`, …) stay English in both languages. They are
ESPHome entity names and MQTT topics; showing them translated would get in the
way of comparing the panel against the controller's own log.

## Naming convention

States carry a prefix: **`GENS_`** for the generator, **`RET_`** for the reactor's
carbonisation phase, **`GAZ_`** for its gasification phase. Without it
`GENS_RUNNING` and `GAZ_RUNNING` would collide — a running engine and a reactor
producing gas are not the same state.

`RET_` and `GAZ_` are **two phases of one vessel**, not two machines. The
carbonisation cycle ends at `RET_COOLDOWN` and what it leaves behind is the
charcoal bed the gasification phase burns, in place. The first consequence is an
interlock: the vessel cannot carbonise and gasify at once, so the two phase
groups are mutually exclusive and `RET_COLD` is the only place the phase may
change. What decides which group may run is `bed`: empty, wood, or char.

The genset is a genuinely separate machine, joined by **single signals**, not by
one transition table. `GAZ_` raises `gas_ready`, which widens the `GENS_READY`
exit condition from `gen_request` to `gen_request and gas_ready`; `GENS_` raises
`engine_drawing`, which the reactor needs because gas does not flow without the
engine drawing it. One combined table would multiply out and be unreadable at
the first bug.

## Ignition before the starter, and a kill that holds

Two sequencing rules the state machine exists to enforce, neither of which a
button can.

**The starter output carries `delay_on`, so the ignition is live a second
before the starter engages.** With both relays closing together the first
compression strokes can happen while the interposing relay is still settling —
the engine turned without spark, battery spent, and one attempt gone off a
budget of three.

It is a property of the output, not a state of its own: a state machine should
not grow a state to express a delay, exactly as the request hold lives in the
input filter rather than in a state timer. `t_attempt` is therefore the whole
attempt window, `t_prestart` of settling plus the cranking itself, so the
starter still turns for three seconds.

**`RELAY-03` shorts the ignition to ground and `GENS_STOPPING` holds it for
`t_kill`.** A single-cylinder engine can ride through a brief short, so the
duration must not depend on how long somebody holds a button. The kill button
on IN-05 is therefore a *request*: it sends the machine to `GENS_STOPPING`,
which energises the relay and holds it, however briefly the button was pressed.
Leaving that state needs the run confirmation gone AND the time served.

`RELAY-03` is energise-to-stop, the opposite polarity to `RELAY-01`, and it is
**not** the inverse of it: it is energised only while stopping and in a fault.
When idle the NC contact of the de-energised `RELAY-01` already holds the short,
so a second coil energised for hours would wear for nothing. Two independent
paths on purpose — one fails safe on loss of power, the other acts positively
on command.

## Sound

Muted by default, toggled from the footer. The machines have recordings, the
interface has synthesis, and the split is deliberate.

Starter, engine and relay snaps are cut from **public-domain recordings** on
Wikimedia Commons by `fetch-sounds.py`, which records the source URLs and the
licence check in its own header. Public domain rather than CC BY-SA on purpose:
these files go into a public repository and onto someone else's domain, so they
must not carry an attribution duty or a share-alike clause.

The interface chimes — state transitions, fault, cycle — are generated by
`gen-sounds.py`. Synthesis is better there: reproducible, consistent in level,
and carrying nobody else's recording.

Loops are WAV, not mp3. Every mp3 encoder pads both ends, which in a loop is
audible as a regular click. The loop point is crossfaded with an equal-power
curve over 150 ms.

A crossfade alone is not enough, and the engine loop proved it. Two things
betray a loop to the ear, and neither of them lives at the splice:

**A level trend.** The recording is of an engine settling after the catch, so
the raw cut ramped down 2.7 dB from start to end and every pass through the loop
was loud at the beginning and quiet at the end. The window is now chosen by
measurement — a linear regression on the 50 ms level track over the whole
recording, looking for the flattest stretch, which is 18.10 s onwards at 0.0 dB
of drift and 1.0 dB of spread. Whatever trend remains is divided out before the
crossfade, as a straight line and never as an instantaneous envelope: the
instantaneous envelope would flatten the firing pulses, and those are the signal.

**A limp in the rhythm.** The envelope autocorrelates at 86.6 ms, one crankshaft
revolution at 690 rpm — a rough idle, so the pattern repeats per revolution
rather than per firing. If the loop length is not a whole number of those, the
beat that crosses the splice is too long or too short and you hear the engine
stumble once per pass. The length is picked by sweeping 1.70 s to 2.25 s in 5 ms
steps and scoring each candidate on exactly that defect: the interval spanning
the splice against the median of all the others. 1.915 s scores 0.0 ms and holds
at crossfades of 20, 30, 40, 60 and 150 ms, so it is phase agreement and not an
artefact of one crossfade width. The worst lengths in the same band are out by
120 to 144 ms.

The relay snaps are WAV as well, for a different reason: a contact snap is an
impulse, and mp3 smears it. Measured on the same cut, a peak normalised to
-3.0 dB came back at -5.9 dBFS after encoding, and raising the bitrate to
192 kbps recovered 0.1 dB of it. They are also kept at the full 44.1 kHz, because
a quarter of the snap's energy sits above 10 kHz.

The relay click took three attempts, each settled by measurement. A dipswitch
recording had **no energy at all below 1.5 kHz** and read as a tick rather than
a contact closing. An installation light switch had the body but the wrong
instrument. What the simulator uses now is **the relay of a stereo amplifier**,
which carries 70 % of its energy between 600 Hz and 1.5 kHz — that band is what
a relay sounds like across a cabinet.

Pull-in and release are two different clicks from the same recording, chosen so
that they read as two movements of one device rather than two devices: 70 % and
54 % of their energy in the same band, decays of 30 and 28 ms. A third click,
just as clean, was rejected for having only 46 % there. Each cut starts 4 ms
before the strike, because the armature is already moving by then, and pull-in
is normalised 1.5 dB above release, because a spring returns more weakly than
a coil pulls.

That one file does not come from the public domain. The author's terms are
"free for your non-profit project", with a commercial licence sold separately,
and this simulator belongs to a foundation — the condition the terms name. The
source, the terms and the date of that decision are in the header of
`fetch-sounds.py`. Everything else in `sounds/` is public domain.

Which sound a signal makes is declared in the YAML, not wired into the
simulator: `sound_loop` plays while the signal is active, `sound_on` and
`sound_off` fire on its edges. The gasifier's blower will get a voice by adding
one line and one file.

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
- **`t_ready`** — minimum dwell in `GENS_READY` after a closed cycle or a fault
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
