# LI-6800 Cotton Gas-Exchange Operating Protocol: Scheme A (Natural-Environment Diurnal Course)

> **Purpose**: Measure cotton leaf gas exchange at multiple times of day under naturally changing light and weather, with special emphasis on reliable leaf-temperature measurements.  
> **Recommended chamber**: 6800-12A clear-top small leaf chamber; the 3 × 3 cm aperture will suit most cotton leaves.  
> **Version**: v1.0, 2026-07-11.  
> **Critical principle**: This scheme is designed to retain real diurnal variation in irradiance, humidity, air temperature, and leaf temperature. Do **not** fix leaf temperature, irradiance, or VPDleaf. Chamber air temperature may be controlled near concurrent ambient temperature to prevent solar heating of the clear-top chamber, but Tleaf must not be held at one value.

---

## 1. What this scheme measures

Scheme A quantifies the leaf's **actual instantaneous performance under the environment at the time of measurement**. It can be used to examine:

- diurnal net assimilation (`A`) and midday depression;
- stomatal conductance (`gsw`), transpiration (`E`), and intercellular CO₂ (`Ci`);
- leaf temperature (`Tleaf/TleafCnd`) relative to air temperature (`Tair`);
- relationships among `VPDleaf`, incident PPFD, A, gsw, and E;
- differences among cultivars, irrigation regimes, nutrient treatments, or stress treatments in the field.

It is not the correct design for asking whether intrinsic photosynthetic capacity changes with time when all measurement conditions are identical. Use Scheme B for that question.

---

## 2. Core design rules

1. Use ambient light through the 6800-12A clear top; remove or disable the artificial light source.
2. Measure leaf temperature directly with the chamber thermocouple; never control Tleaf in Scheme A.
3. Keep chamber air near concurrent ambient temperature to prevent artificial solar heating.
4. Do not hold VPDleaf constant across the day.
5. Prefer ambient CO₂ supplied through a buffer volume; if CO₂ is controlled, report that the measurement is no longer fully ambient-CO₂.
6. Rotate or randomize treatment order within each time block.
7. Treat thermocouple contact as a primary quality-control criterion because leaf temperature enters calculations of gsw, Ci, and VPDleaf.

---

## 3. Equipment and consumables

### 3.1 Required equipment

- LI-6800 console;
- LI-6850 sensor head;
- head communication cable and air-supply tube bundle;
- 6800-12A clear-top chamber;
- 3 × 3 cm aperture set; use 2 × 3 cm if the available lamina is too narrow;
- leaf-temperature thermocouple connected to `T1`;
- charged batteries and at least one spare battery;
- an intake buffer volume of at least 4 L, preferably about 20 L for field work;
- tubing and the appropriate console inlet fitting;
- FAT/FAT32 USB drive;
- plant tags, marker, field sheet, and timer;
- independent temperature/RH sensor or weather station;
- optional second thermocouple on `T2` for ambient temperature;
- optional LI-190R external quantum sensor for `Qamb_out`.

### 3.2 Gas-conditioning materials

- active desiccant in H₂O SCRUB;
- water in the H₂O ADD humidifier column, appropriate to the column type;
- active soda lime in CO₂ SCRUB;
- a new 8-g CO₂ cartridge is usually unnecessary for Scheme A because CO₂ control is normally Off.

### 3.3 Safety

- Never connect or disconnect the head cable while the instrument is powered.
- CO₂ cartridges are pressurized; keep them below 50 °C and out of direct sun.
- Wet soda lime is caustic; wear gloves and eye protection.
- The humidifier column must not leak liquid water.
- Remove the Nafion humidifier column overnight and before transport or storage.

---

## 4. Cotton sampling design

### 4.1 Leaf selection

Choose one biological rule and use it throughout the study:

- **Canopy physiology**: the youngest fully expanded, healthy, sun-exposed upper main-stem leaf;
- **boll–leaf source relationships**: the subtending leaf at the same fruiting branch and fruiting position;
- **seedling work**: the youngest fully expanded main-stem leaf.

Cotton leaves are lobed and have prominent veins. Place the aperture over intact interveinal lamina, avoid the midrib and large secondary veins, and keep leaf position and developmental status consistent.

### 4.2 Stomatal ratio K

Cotton is amphistomatous, but adaxial and abaxial stomatal densities vary among genotypes, leaf ages, and growth VPD. If no direct stomatal data are available, use `K = 0.5` as a provisional approximation and state this in the methods. A stronger protocol measures both surfaces and sets K from the study material.

### 4.3 Replication and time points

A practical starting design is:

- at least 8–10 independent plants per treatment;
- one tagged leaf per plant as the biological replicate;
- 07:00, 09:00, 11:00, 13:00, 15:00, and 17:00;
- add 10:00, 12:00, and 14:00 when midday depression is the central question.

Adjust the schedule to local sunrise, sunset, and climate.

### 4.4 Treatment order

Do not measure treatments in the same sequence at every time point. A rotating example is:

| Time | Example treatment order |
|---|---|
| 07:00 | Control → T1 → T2 → T3 |
| 09:00 | T1 → T2 → T3 → Control |
| 11:00 | T2 → T3 → Control → T1 |
| 13:00 | T3 → Control → T1 → T2 |

Randomize plant order within treatment. If one nominal time block takes too long, reduce the sample count, add instruments, or use blocks and retain the exact measurement time in the analysis.

---

## 5. Preparation on the previous day

1. Tag all plants and leaves.
2. Select a day with clear or consistently overcast conditions; rapidly fluctuating cloud is poor for ambient-light diurnal work.
3. Charge all batteries.
4. Format the USB drive as FAT/FAT32; exFAT is not supported.
5. Inspect clear windows, gaskets, apertures, and thermocouple.
6. Build the buffer volume:
   - use a clean, dry container that has never held chemicals;
   - make two holes in the lid;
   - route the instrument intake tube to the bottom of the container;
   - leave the second hole open to the environment;
   - keep all other parts sealed;
   - place the buffer upwind, away from the operator and soil surface, preferably about 1 m above ground.
7. Prepare a field sheet with date, exact time, treatment, plant, leaf, leaf position, cloud, ambient T, ambient RH, and remarks.

---

## 6. Physical assembly — instrument powered Off

### 6.1 Chemical columns

1. Verify the H₂O SCRUB, H₂O ADD, and CO₂ SCRUB columns are in the correct positions.
2. Replace or regenerate exhausted desiccant.
3. Fill a Nafion humidifier column with filtered or deionized water and tighten the cap; remove it immediately if any leakage is seen.
4. Replace exhausted soda lime and keep dust out of the manifold.
5. Keep O-rings, threads, and sealing surfaces clean and dry.

### 6.2 Console-to-head connections

1. Confirm the LI-6800 is powered Off.
2. Connect one end of the head cable to `HEAD 1` or `HEAD 2` on the console and the other to the sensor head.
3. Align each red dot upward and push straight in.
4. Connect the air tube between console `AIR OUT` and the head inlet.
5. Pull gently on the tubing to confirm it is locked.
6. Route the bundle to avoid kinks and snagging on cotton plants.

### 6.3 Install the 6800-12A chamber

1. Align the chamber on the sensor head.
2. Use only the original captive mounting screws and tighten evenly.
3. Install and check the latch screws.
4. Install matching 3 × 3 cm upper and lower apertures in the same orientation.
5. Use flat, undamaged gaskets; white gaskets are recommended for the clear-top chamber.
6. If changing to 2 × 3 or 1 × 3 cm, replace both apertures and the matching bottom plate and select the same configuration in software.

### 6.4 Leaf-temperature thermocouple

1. Insert the T1 thermocouple upward through the lower chamber.
2. Connect it to `T1` on the head.
3. Set the junction approximately 2 mm above the gasket as a starting position.
4. It must lightly contact the abaxial leaf surface after closure without contacting metal, gasket, or a major vein.
5. Install the connector cover.
6. For an ambient thermocouple, connect T2 and configure it as `T2 out`; shield it from direct radiation while allowing ventilation.

### 6.5 Light sensors

1. Verify the 6800-12A internal ambient-light sensor responds.
2. If an external LI-190R is used, mount it on the head, remove the red cap, connect it to PAR as appropriate for the installed configuration, enter the calibration multiplier under `Environment > Light > Ambient`, and confirm that shading it lowers `Qamb_out`.
3. Do not improvise splitters if the PAR port is occupied; follow the installed accessory configuration or LI-COR support guidance.

### 6.6 Buffer volume

1. Connect the buffer outlet to the console intake using the correct fitting.
2. Keep the environmental inlet open and unobstructed.
3. Place the buffer in the measured environment, upwind of the operator.
4. After startup, verify that `CO2_r` and `H2O_r` are more stable than with direct intake.

---

## 7. Startup and daily system checks

### 7.1 Power on

1. Confirm all cables, tubes, chamber parts, and thermocouples are connected.
2. Insert batteries or connect approved external power.
3. Power on.
4. Wait for detection of the console, head, and chamber.
5. Verify date, time, and time zone.

### 7.2 Chamber recognition

Under `Start Up > Chamber Setup` or `Constants > System Constants`, confirm:

- the detected `ChType` is 6800-12A;
- aperture size and orientation are correct;
- after any chamber or aperture change, run the Chamber Leak Test.

### 7.3 Warmup Tests

1. Close the empty chamber.
2. Go to `Start Up > Warmup/System Tests`.
3. Select `Warmup Tests` and tap `Start`.
4. Allow approximately 10–15 min.
5. Review flow, valve, analyzer, fan, humidity, and heat-exchanger results.
6. Resolve critical failures before collecting data; common causes include loose air tubes, leaking column caps, exhausted chemicals, poor chamber installation, or debris in the fan.

### 7.4 Chamber Leak Test

Run `Start Up > System Tests > Chamber Leak` with the empty chamber closed. Inspect apertures, gaskets, mounting screws, and closure if the test fails. Repeat after any aperture or chamber change.

---

## 8. Chamber setup and constants

### 8.1 Gas Exchange

| Item | Scheme A setting |
|---|---|
| Chamber type | 6800-12A, verify automatic detection |
| Geometry | `Broadleaf` |
| Leaf area `S` | Actual enclosed area; 9 cm² only when the 3 × 3 aperture is fully filled |
| Stomatal ratio `K` | 0.5 provisionally or study-specific measured value |
| Oxygen | 21% |

If the aperture is not filled, photograph the enclosed region with a scale and correct S before analysis or recompute the spreadsheet.

### 8.2 Leaf Temperature

Under `Constants > Leaf Temperature`:

- select `Measured`;
- use T1 as the leaf-temperature source;
- set T2 to `T2 out` if it measures ambient air;
- use `Energy Balance` only when physical contact cannot be achieved;
- retain `Tleaf`, `TleafCnd`, and `TleafEB` in the data.

### 8.3 Leaf Light

Under `Constants > Leaf Light` or `Environment > Light > Ambient`:

- choose `Sun + Sky` for natural sunlight;
- retain default absorptance unless measured directly;
- verify `Qamb_in` responds to shading;
- verify `Qamb_out` when an external sensor is installed.

---

## 9. Complete Environment settings for Scheme A

### 9.1 Flow

Under `Environment > Flow`:

| Setting | Value |
|---|---:|
| Flow | On |
| Pump speed | Auto |
| Chamber flow | 500 μmol s⁻¹ |
| Overpressure | 0.1 kPa; 0.2 kPa if required |

For very low-flux stressed cotton, a pilot may justify 300 μmol s⁻¹ to increase ΔCO₂ and ΔH₂O. Once selected, use the same flow for all treatments and times and recheck matching and stability.

### 9.2 Fan

Under `Environment > Fan`:

- Mixing fan: On
- Fan speed: 10,000 rpm

Do not reduce fan speed merely to imitate natural wind; the fan is required for chamber mixing and boundary-layer calculations.

### 9.3 CO₂ — ambient mode

Under `Environment > CO2`:

- CO₂ injector: Off
- supply ambient air through the buffer volume;
- stand downwind and avoid speaking near the inlet;
- log both `CO2_r` and `CO2_s`.

If ambient CO₂ is unusably variable, an explicitly modified “near-ambient controlled” mode is possible:

1. turn CO₂ control Off and observe stable `CO2_r` while away from the inlet;
2. turn CO₂ control On;
3. control `CO2_r` to that value;
4. update the value for each time block;
5. report that natural CO₂ variation was removed.

### 9.4 H₂O — retain environmental humidity variation

Do not set one VPDleaf for the entire day.

**Option 1: fully ambient intake**

- H₂O: Off
- use buffered ambient air;
- monitor high RH, condensation, and AutoDry.

**Option 2: stabilized ambient tracking**

1. temporarily set H₂O Off;
2. allow the upwind buffer to stabilize and read current `H2O_r`;
3. turn H₂O On;
4. control `H2O_r` to the measured ambient value;
5. repeat at each time block;
6. never use one fixed VPDleaf across the day.

The mixing fan removes much of the pre-existing boundary layer. If gsw declines rapidly after clamping, chamber humidity may be too different from the leaf's previous boundary-layer humidity; adjust H2O_r toward the concurrent field condition. Do not log during RH >90% warnings or AutoDry.

### 9.5 Temperature — natural leaf temperature without chamber overheating

Never control Tleaf in Scheme A.

**Preferred procedure**:

1. measure ambient air with T2 near the chamber;
2. set Temperature On;
3. control `Tair`;
4. set Tair to the concurrent T2 ambient temperature;
5. update each time block;
6. continue measuring leaf temperature directly with T1.

If Tair control is unsuitable, control Txchg after a pilot establishes the Txchg that keeps Tair near ambient.

Alternative: Temperature Off, with an independent ambient measurement. If chamber Tair is materially warmer than ambient because of solar loading, the observation is not a valid natural-environment measurement. Predefine a project tolerance, for example approximately ±1 °C, and report it.

### 9.6 Light

Under `Environment > Light`:

- artificial light source Off or physically removed;
- ambient source = `Sun + Sky`;
- log `Qamb_in`; log `Qamb_out` if available;
- use chamber-internal PPFD for analysis because the clear top reduces incident light;
- keep chamber orientation fixed and avoid shadows from the operator or instrument.

### 9.7 Auto Controls

Check `Environment > Auto Controls` and stop any residual program that could override CO₂, H₂O, temperature, or light settings.

---

## 10. IRGA matching

### 10.1 Before measurement

1. After warmup, open `Measurements`.
2. Tap `Match IRGAs`.
3. Perform `Manual Match` before the first formal block.
4. Wait for completion before returning to Measurements.

### 10.2 Range Match

When valid CO₂ and H₂O range-match data are available:

- implement range matching;
- set H₂O point matching to `Never match`;
- use CO₂ range matching and consider a point match about every 30 min when head temperature changes;
- rematch after strong environmental changes or systematic drift;
- do not log leaf data during matching.

### 10.3 Without Range Match

Under `Log Setup/Log Files > Match Options`:

- CO₂: `Only match if`; the uploaded quick guide gives example thresholds of 10 ppm difference, 100 ppm reference change, and 10 min elapsed;
- H₂O: `Never match`;
- alternatively, perform one manual match at the start of each block.

---

## 11. Log Setup / Log Files

Menu wording varies among Bluestem versions.

### 11.1 Stability

Suggested starting criteria:

| Variable | Slope limit | Period |
|---|---:|---:|
| CO2R & CO2S | 2 | 20 s |
| H2OR & H2OS | 2 | 20 s |
| A.GasEx | 1 | 20 s |
| gsw.GasEx | 0.1 | 20 s |

A 4/4 display means only that these criteria are met. Inspect A, gsw, Tleaf, and VPDleaf traces to confirm physiological stability.

### 11.2 Logging options

- enable `Also log data to Excel file`;
- if fluorescence is not measured, use `Flr Action at log = 0: Nothing`;
- enable `Prompt on manual log`;
- create user constants for Treatment, Plant_ID, Leaf_ID, Time_Block, Leaf_Position, Operator, Weather_Code, and Notes;
- do not accidentally treat `Const:S` as a changing row variable; update S for each leaf or correct it later when area varies.

### 11.3 File structure

One practical structure is:

```text
2026-07-11_Cotton_Diurnal_A/
├── 0700_all_treatments
├── 0900_all_treatments
├── 1100_all_treatments
├── 1300_all_treatments
├── 1500_all_treatments
└── 1700_all_treatments
```

A single all-day file is also acceptable when user constants unambiguously identify every record.

---

## 12. Trial-leaf check

At the first time point, use a nonexperimental cotton leaf.

1. Verify empty-chamber settings.
2. Record ambient T2, RH, wind, and cloud.
3. Select a leaf with the same developmental status as experimental leaves.
4. Avoid changing its orientation or light history.
5. Put the chamber in Parked position and align interveinal lamina.
6. Close the chamber and confirm thermocouple contact.
7. Observe for 2–3 min:
   - plausible continuous Tleaf;
   - stable Qamb_in;
   - no breathing artifact in CO2_r;
   - A and gsw approaching a plateau;
   - no excessive RH;
   - Tair close to ambient.
8. Correct humidity or thermocouple problems before formal data collection.
9. Lock the basic daily procedure after the trial; do not change flow, fan, or chamber configuration midway without documenting and restarting comparability checks.

---

## 13. Procedure for each formal leaf

1. Confirm Treatment, Plant_ID, Leaf_ID, and leaf position.
2. Record pre-clamp environment and cloud status.
3. Avoid shading or moving the leaf before enclosure.
4. Open the chamber.
5. Position flat interveinal lamina, avoiding the midrib.
6. Use Parked position to adjust placement.
7. Close fully and inspect the seal.
8. Verify T1 contact with the abaxial surface.
9. Keep chamber orientation unchanged.
10. Inspect real-time A, gsw, E, Ci, Tleaf, Tair, VPDleaf, CO2_r, H2O_r, and Qamb_in.
11. Wait until:
    - Stability is 4/4;
    - A has no sustained one-direction trend;
    - gsw is no longer changing rapidly;
    - Tleaf and VPDleaf do not jump;
    - no cloud transition has just occurred.
12. Press Log on the console or hold the head Log button until the record is confirmed.
13. Complete prompt fields.
14. Open the chamber gently.
15. Inspect the leaf for damage and annotate any imprint or injury.
16. Proceed to the next plant without changing settings.

Outdoor survey measurements should often be completed within roughly 60–90 s per leaf, but never log an unstabilized leaf merely to meet a time target.

---

## 14. Between time blocks

Before each block:

1. inspect battery and chemical status;
2. check buffer position and tubing;
3. update the Tair setpoint to concurrent ambient temperature, never Tleaf;
4. if tracking H2O_r, redetermine and update the ambient H2O_r target;
5. inspect Qamb_in, Qamb_out, T2, and weather data;
6. point-match CO₂ when needed or confirm range matching;
7. open the correct log file;
8. rotate treatment order;
9. use a quick trial leaf to verify thermocouple contact and environmental behavior.

---

## 15. Required output variables

### Gas exchange

- A, gsw, E, Ci;
- CO2_r and CO2_s;
- H2O_r and H2O_s;
- chamber RH.

### Temperature and water status

- Tleaf;
- TleafCnd;
- TleafEB;
- Tair;
- Txchg;
- T2 or independent ambient temperature;
- VPDleaf.

### Light and instrument status

- Qamb_in/Qin;
- Qamb_out if available;
- flow setpoint and measured flow;
- ΔP;
- fan speed;
- leak diagnostic variables;
- date and exact time;
- S, K, Geometry;
- match status.

### Derived quantities

- ΔT = TleafCnd − ambient temperature;
- WUE = A/E;
- iWUE = A/gsw;
- Ci/Ca.

---

## 16. Leaf-temperature quality control

Flag and preferably repeat observations when:

- Tleaf is missing or near 9999.9;
- Tleaf jumps without corresponding environmental change;
- the junction does not contact the leaf;
- it lies on a large vein;
- Tleaf is physiologically implausible;
- TleafCnd is not using the intended T1 source;
- chamber Tair is substantially warmer than ambient;
- high-RH warning, AutoDry, or condensation occurs.

Retain Tleaf, TleafCnd, and TleafEB. TleafCnd is the most important temperature for auditing gsw, Ci, and VPDleaf calculations.

---

## 17. Troubleshooting

### Unusual A

Check S, aperture fill, vein-induced leaks, IRGA matching, flow, plant health, recent light history, and temperature contact.

### gsw declines continuously

Possible explanations include true drought/high-VPD response, chamber air drier than the prior boundary layer, a recent shade-to-sun transition, excessive enclosure time, or clamp injury. Distinguish biological response from chamber artifact.

### CO2_r fluctuates

Check buffer size and leaks, move it upwind, keep operators away, avoid vehicle exhaust, and consider near-ambient CO2_r control if necessary, with explicit reporting.

### High RH or AutoDry

Stop logging, check dew point and chamber temperature, reduce water input, inspect the humidifier, allow recovery, rematch, and repeat the leaf.

### Cloud transitions

Do not log during abrupt PPFD changes. Wait for the leaf to restabilize. If clouds fluctuate throughout the day, reschedule or use Scheme B.

### USB transfer failure

The head must remain connected to the console; the drive must be FAT/FAT32. Use `Tools > Manage Files > Copy files to USB` and tap `Eject` before removal.

---

## 18. End-of-day data transfer and shutdown

1. Tap `Close Log`.
2. Wait until the Excel file is completely written.
3. Insert a FAT/FAT32 USB drive.
4. Open `Tools > Manage Files`.
5. Select `Copy files to USB`.
6. Copy the entire day folder and logs.
7. Confirm the files appear on the USB side.
8. Tap `Eject` and remove the drive.
9. Optionally create a full backup including user data, configuration, and diagnostics.
10. Use Standby during a short break.
11. At the end of the day, tap the power button once and select `Shutdown`.
12. After power-off, remove and empty the Nafion humidifier column, remove plant debris, leave the chamber Parked rather than tightly closed, and store the instrument out of heat and direct sun.

For long storage, remove batteries and the CO₂ cartridge and follow the official storage protocol.

---

## 19. Field data sheet

| Date | Exact time | Treatment | Plant | Leaf | A | gsw | E | Ci | TleafCnd | Tair | Ambient T2 | VPDleaf | Qamb_in | CO2_r | Chamber RH | Cloud | Notes |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|

---

## 20. Analysis recommendations

- Use repeated-measures or mixed-effects models when the same leaf is measured repeatedly.
- Include Treatment, Time, and Treatment × Time as fixed effects and Plant/Leaf as a random effect.
- Retain exact measurement time rather than only nominal time blocks.
- Because irradiance, VPDleaf, and Tleaf covary, a simple A-versus-Tleaf correlation does not establish temperature causality.
- Consider covariates Qamb_in, VPDleaf, TleafCnd, and CO2_r.
- Lock exclusion rules for cloud transitions, failed thermocouple contact, AutoDry, and instability before analysis.

---

## 21. One-page checklist

### Before starting

- [ ] Cotton leaves tagged and order randomized
- [ ] Head cable connected while powered Off
- [ ] 6800-12A, aperture, gaskets, and T1 correct
- [ ] Buffer upwind
- [ ] Warmup Tests passed
- [ ] Chamber Leak Test passed
- [ ] ChType, S, K, and Geometry correct
- [ ] Leaf temperature source = Measured
- [ ] Flow 500, ΔP 0.1, fan 10,000
- [ ] CO₂ Off or modified near-ambient mode documented
- [ ] VPDleaf not fixed
- [ ] Tleaf not controlled; Tair near ambient
- [ ] Artificial light Off; Qamb_in valid
- [ ] IRGAs matched
- [ ] Log file open

### Each leaf

- [ ] Correct sample identity
- [ ] Recent light history preserved
- [ ] Major veins avoided
- [ ] Thermocouple contacts lamina
- [ ] Chamber orientation unchanged
- [ ] A, gsw, Tleaf, and VPDleaf stable
- [ ] No cloud transition, condensation, or AutoDry
- [ ] Prompts completed

### End

- [ ] Close Log
- [ ] Excel writing completed
- [ ] USB copied and ejected
- [ ] Normal Shutdown
- [ ] Humidifier removed
- [ ] Chamber Parked

---

## 22. References

1. User-provided *LI-6800 Quick Start Experimental Guide*, especially the diurnal/seasonal survey protocol, buffer-volume appendix, and range-match appendix.
2. [LI-COR: Assembling the LI-6800](https://www.licor.com/support/LI-6800/topics/assembly.html)
3. [LI-COR: Installing the small leaf chamber](https://www.licor.com/support/LI-6800/topics/chamber-3x3.html)
4. [LI-COR: Preparing for measurements](https://www.licor.com/support/LI-6800/topics/making-leaf-level-measurements.html)
5. [LI-COR: Survey measurement considerations](https://www.licor.com/support/LI-6800/topics/leaf-measurement-examples-intro.html)
6. [LI-COR: Leaf chamber software controls](https://www.licor.com/support/LI-6800/topics/leaf-measurement-controls.html)
7. [LI-COR: H₂O control](https://www.licor.com/support/LI-6800/topics/environment-h2o-control.html)
8. [LI-COR: Matching the IRGAs](https://www.licor.com/support/LI-6800/topics/matching-the-analyzers.html)
9. [LI-COR: Warmup tests](https://www.licor.com/support/LI-6800/topics/system-tests-warmup.html)
10. [LI-COR: Transferring files](https://www.licor.com/support/LI-6800/topics/file-transfer.html)
11. [LI-COR: Storing the LI-6800](https://www.licor.com/support/LI-6800/topics/storing.html)
12. Devi MJ et al. 2018. [Transpiration Response of Cotton to Vapor Pressure Deficit and Its Relationship With Stomatal Traits](https://pmc.ncbi.nlm.nih.gov/articles/PMC6218332/).
13. Echer FR et al. 2015. [Cotton leaf gas exchange responses to irradiance and leaf aging](https://link.springer.com/article/10.1007/s10535-015-0484-3).
14. Pallas JE et al. 1967. [Photosynthesis, transpiration, leaf temperature, and stomatal activity of cotton plants under varying water potentials](https://pubmed.ncbi.nlm.nih.gov/16656488/).
