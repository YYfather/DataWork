# LI-6800 Cotton Gas-Exchange Operating Protocol: Scheme B (Standardized-Environment Diurnal Course)

> **Purpose**: Compare cotton leaf gas exchange at multiple times of day while holding chamber CO₂, irradiance, leaf temperature, and VPD constant.  
> **Recommended chamber/light**: 6800-12A clear-top small leaf chamber with the 6800-02 red/blue light source; the 6800-01A fluorometer chamber is an alternative.  
> **Version**: v1.0, 2026-07-11.  
> **Critical interpretation**: Scheme B reports performance under the selected standardized chamber environment, not the leaf's actual field photosynthesis at that moment. Leaf temperature remains a critical variable, but here it is controlled to one common setpoint.

---

## 1. What Scheme B is designed to answer

By fixing the measurement environment, Scheme B minimizes variation caused by changing sunlight, ambient temperature, humidity, and CO₂. It can test:

- whether cotton leaves show time-of-day physiology beyond the immediate weather;
- treatment differences in potential photosynthetic performance under a common environment;
- morning, midday, and afternoon differences in A, gsw, E, Ci, and water-use efficiency;
- intrinsic effects of heat, drought, nutrition, or genotype.

Use Scheme A to study real natural leaf temperature and ambient performance. Use Scheme B to compare capacity at a common Tleaf and common chamber environment.

---

## 2. Recommended standardized setpoints

The table below is a usable starting recipe for field-grown cotton. Validate it on 3–5 representative plants before formal measurement.

| Control | Working default | Notes |
|---|---:|---|
| Flow | 500 μmol s⁻¹ | A pilot may justify 300 for very low-flux stressed leaves; then use it for every sample |
| ΔP | 0.1 kPa | 0.2 kPa may be used if needed |
| Fan | 10,000 rpm | Ensures chamber mixing |
| CO₂ target | `CO2_s = 400 μmol mol⁻¹` | A preregistered 420 is also acceptable; never change midway |
| H₂O target | `VPDleaf = 1.5 kPa` | Usually within a suitable humidity range; monitor condensation |
| Leaf temperature | `Tleaf = 30 °C` | Working cotton default; 28 °C may be selected before the study if justified |
| Irradiance | 1500 μmol m⁻² s⁻¹ | Validate with a cotton light-response pilot |
| Color Spec | `r90` | Approximately 90% red and 10% blue |
| O₂ | 21% | Ambient oxygen |
| Geometry | Broadleaf | Cotton leaf geometry |
| Leaf area S | 9 cm² or actual area | 9 cm² only when the 3 × 3 aperture is completely filled |
| K | 0.5 provisionally | Prefer a study-specific stomatal ratio |

### 2.1 Why the light level needs a pilot

Cotton light saturation depends on genotype, leaf age, nitrogen, water status, and growth light. Published work often shows small increases above roughly 1000 μmol m⁻² s⁻¹ in sun leaves, but old, shaded, or stressed leaves can saturate earlier. A setpoint of 1500 is an operational starting point, not a universal cotton constant.

Pilot rule:

- if A is nearly identical at 1200 and 1500, choose 1200 to reduce photoinhibition risk and cooling demand;
- if A continues to increase at 1500 without decline, 1500 is reasonable;
- never change the formal setpoint among time points.

---

## 3. Equipment and consumables

### 3.1 Required

- LI-6800 console;
- LI-6850 sensor head;
- head communication cable and air tube;
- 6800-12A chamber;
- 6800-02 red/blue light source;
- 3 × 3 cm aperture and matching bottom plate;
- T1 leaf-temperature thermocouple;
- high-quality oil-free 8-g CO₂ cartridges, or an external pure CO₂ cylinder with the official adapter and regulator;
- desiccant, humidifier column, and soda lime;
- batteries and spares;
- FAT/FAT32 USB drive;
- labels, field sheets, and timer;
- optional buffer volume;
- optional T2 ambient thermocouple and LI-190R for recording pre-clamp environment.

### 3.2 6800-01A alternative

When using the 6800-01A fluorometer chamber:

- set S according to the 6 cm² or 2 cm² aperture;
- control actinic light under the Fluorometry/Light menu;
- when fluorescence is not required, set `Flr Action at log = 0: Nothing`;
- fluorescence flashes and dark adaptation require a separate fluorescence protocol.

---

## 4. Cotton experimental design

### 4.1 Leaf rule

Use one consistent category:

- upper-main-stem youngest fully expanded sun leaf for canopy physiology;
- a matched subtending leaf at the same fruiting branch and position for boll–leaf studies;
- avoid midribs, large veins, lesions, insect holes, and curled tissue.

### 4.2 Repeated or independent leaves

**Repeated-measures design**: measure the same tagged leaf through the day. Use the same flat lamina region when no damage occurs, or preregister adjacent nonoverlapping interveinal regions if repeated clamping leaves an imprint. Include Plant/Leaf as a random effect.

**Independent-sampling design**: use different plants or leaves at each time. This avoids repeated enclosure but requires more biological material. Multiple leaves from one plant are not fully independent replicates.

### 4.3 Time and order

A practical schedule is 07:00, 09:00, 11:00, 13:00, 15:00, and 17:00. Rotate or randomize treatment order within each block and complete the block as quickly as practical.

---

## 5. Previous-day preparation

1. Tag plants, leaves, and possible chamber positions.
2. Finalize and preregister all setpoints; do not adjust them casually during formal measurement.
3. Charge batteries and prepare spares because light and temperature control are power intensive.
4. Prepare sufficient CO₂. An 8-g cartridge is typically useful for about 8 h after piercing even if control is intermittently Off.
5. Inspect desiccant, humidifier, and soda lime.
6. Format the USB drive as FAT/FAT32.
7. Define file names and user constants.
8. Prepare pilot sheets for light response and induction time.

---

## 6. Physical assembly — power Off

### 6.1 Gas-conditioning columns

1. Fill H₂O SCRUB with active desiccant.
2. Fill the Nafion H₂O ADD column with filtered or deionized water; tighten the cap and reject any leakage.
3. Fill CO₂ SCRUB with active soda lime without introducing dust.
4. Inspect and clean O-rings and threads.

### 6.2 CO₂ cartridge

1. Keep the console shaded and stable.
2. Insert a high-quality oil-free 8-g cartridge, large end first.
3. Tighten to resistance and quickly turn approximately another half turn to pierce.
4. record the new-cartridge status.
5. Never remove a pressurized cartridge rapidly; vent it slowly according to the official manual.

For an external cylinder, use the official adapter and correct regulator pressure and run the relevant Soda Lime–CO₂ system test.

### 6.3 Head cable and air tube

1. Confirm power is Off.
2. Connect the head cable to `HEAD 1` or `HEAD 2` and to the sensor head, red dots upward.
3. Connect the air tube from console `AIR OUT` to the head.
4. Confirm full engagement and no kinks.
5. Never unplug the head cable while powered.

### 6.4 Install the 6800-12A

1. Mount the chamber with the original captive screws and tighten evenly.
2. Install matching 3 × 3 cm upper/lower apertures and bottom plate.
3. Make sure aperture size and orientation match.
4. Install clean white gaskets and inspect the seal.
5. Confirm Open, Parked, and Closed positions work correctly.

### 6.5 T1 thermocouple

1. Insert T1 through the lower chamber and connect it to `T1`.
2. Start with the junction about 2 mm above the gasket.
3. It must lightly contact the abaxial lamina after closure.
4. Avoid major veins and metal surfaces.
5. If contact is unreliable, do not use Tleaf control until the geometry is corrected.

### 6.6 6800-02 light source

1. Mount the 6800-02 on the 6800-12A.
2. Connect its cable to the head `LS` connector.
3. Secure the cable to prevent strain.
4. After startup, verify detection under `Environment > Light > Head Light Source`.
5. Never look directly into the LED source.

### 6.7 Optional buffer volume

Although CO₂ and H₂O are controlled, a buffer can reduce inlet disturbances and dust. Connect and position it as described in Scheme A.

---

## 7. Startup, tests, and recognition

1. Inspect all physical connections.
2. Insert batteries or connect approved power and start the instrument.
3. Check date, time, and time zone.
4. Under `Start Up > Chamber Setup`, confirm:
   - 6800-12A;
   - 6800-02 detection;
   - correct aperture and orientation;
   - Complete Gas Exchange;
   - O₂ = 21%.
5. Close the empty chamber.
6. Run `Start Up > Warmup/System Tests > Warmup Tests`.
7. Allow 10–15 min and resolve critical failures.
8. Run Chamber Leak Test.
9. If a new CO₂ source was installed, run the relevant CO₂/Soda Lime test.
10. Verify fan, heat exchanger, and humidity control performance.

---

## 8. Constants

### 8.1 Gas Exchange

Under `Constants > Gas Exchange`:

| Parameter | Setting |
|---|---|
| ChType | 6800-12A |
| Geometry | Broadleaf |
| S | 9 cm² or actual enclosed area |
| K | 0.5 provisionally or measured value |
| O₂ | 21% |

Correct or recompute S whenever the cotton leaf does not fill the aperture.

### 8.2 Leaf Temperature

Under `Constants > Leaf Temperature`:

- select `Measured`;
- use T1 as the control and computation source;
- verify `TleafCnd` source;
- do not continue formal Tleaf control with poor contact.

### 8.3 Leaf Light

- select the attached LED source as the leaf-light source;
- retain default absorptance unless measured;
- verify Total Leaf Q includes the intended 6800-02 source.

---

## 9. Complete Environment settings for Scheme B

### 9.1 Flow

`Environment > Flow`

- Flow: On
- Pump Speed: Auto
- Flow: 500 μmol s⁻¹
- ΔP: 0.1 kPa

A pilot may support 300 μmol s⁻¹ for low-flux material, but the same flow must then be used everywhere.

### 9.2 Fan

`Environment > Fan`

- Mixing fan: On
- Fan speed: 10,000 rpm

### 9.3 CO₂

`Environment > CO2`

- CO₂ injector: On
- target: preferably `CO2_s`
- setpoint: 400 μmol mol⁻¹
- Soda Lime/Scrub: Auto or enabled as required by the installed software

CO2_s control exposes leaves to a common chamber CO₂ despite differences in A. CO2_r control can be faster but is appropriate only after a pilot with samples of similar assimilation.

A fixed 420 μmol mol⁻¹ protocol is also valid if selected before the study and used throughout.

### 9.4 H₂O

`Environment > H2O`

- H₂O: On
- control: VPDleaf
- setpoint: 1.5 kPa

Procedure:

1. bring Tleaf near 30 °C;
2. enable VPDleaf control;
3. confirm chamber RH is achievable without condensation;
4. do not log during setpoint override, high-RH warning, or AutoDry;
5. never set VPD to zero;
6. in persistently humid conditions, a fixed RH_air of 60–70% can be used instead, provided it is identical for all measurements and actual VPDleaf is reported.

### 9.5 Temperature

`Environment > Temperature`

- Temperature: On
- control: Tleaf
- setpoint: 30.0 °C

Procedure:

1. verify T1 contact;
2. enter 30.0 °C;
3. wait for Tleaf, Tair, and Txchg to stabilize;
4. keep the target above the dew point;
5. if midday conditions prevent 30 °C control, do not selectively accept warmer leaves. Shade the head without shading the plant, improve ventilation, or select a higher all-day setpoint such as 32 °C and restart the formal experiment consistently.

### 9.6 Light

For 6800-02:

`Environment > Light > Head Light Source`

- Control Mode: Setpoint/On
- Setpoint: 1500 μmol m⁻² s⁻¹
- Color Spec: r90

For 6800-01A:

`Environment > Fluorometry/Light`

- Control Mode: Setpoint
- Setpoint: 1500 μmol m⁻² s⁻¹
- Color Spec: r90

Turn the target light on before clamping. A leaf moved from low ambient light into 1500 may require substantial induction. A 4/4 stability flag alone does not prove physiological steady state.

### 9.7 Auto Controls

Stop all residual Auto Controls and background programs that could alter CO₂, H₂O, temperature, or light. Scheme B uses fixed setpoints.

---

## 10. Matching and Range Match

### Recommended workflow

1. Perform Manual Match after warmup.
2. Acquire and implement valid CO₂ and H₂O Range Match data before the experiment.
3. Set H₂O point match to Never match.
4. Use CO₂ range matching and point-match when head temperature changes substantially.
5. Check match status at the start of each time block.

Without Range Match:

- set CO₂ to `Only match if` or match manually at each block;
- set H₂O to `Never match`;
- never log during the match sequence.

---

## 11. Stability and logging

### 11.1 Stability criteria

Suggested starting values:

| Variable | Slope limit | Period |
|---|---:|---:|
| CO2R & CO2S | 1 | 20 s |
| H2OR & H2OS | 1 | 20 s |
| A.GasEx | 1 | 20 s |
| gsw.GasEx | 0.1 | 20 s |

### 11.2 Logging options

- enable `Also log data to Excel file`;
- with 6800-01A and no fluorescence, use `Flr Action at log = 0: Nothing`;
- enable `Prompt on manual log`;
- use Treatment, Plant_ID, Leaf_ID, Time_Block, Leaf_Position, Induction_Time, and Notes as user constants;
- use one file per block or one all-day file with complete metadata.

---

## 12. Mandatory pilot work

### 12.1 Light setpoint

On 3–5 representative cotton leaves, test 1000, 1200, 1500, and 1800 μmol m⁻² s⁻¹ while holding CO₂, Tleaf, and VPDleaf constant. Select the lowest irradiance that removes light limitation without reducing A or causing thermal stress.

### 12.2 Induction time

At morning, midday, and afternoon:

1. clamp a representative leaf from its natural condition into the standardized chamber;
2. record A and gsw from closure to steady state;
3. define one objective rule for formal work, for example a minimum of 3 min plus stable A, gsw, Tleaf, and VPDleaf;
4. expect 10–20 min or longer when a low-light leaf enters high actinic light;
5. use the same rule for all treatments.

### 12.3 Temperature feasibility

Test the selected Tleaf setpoint during the hottest expected period. If it cannot be achieved, choose an all-day achievable setpoint before the formal experiment.

---

## 13. Before each time block

1. inspect battery, CO₂ supply, desiccant, humidifier, and soda lime;
2. inspect chamber and T1;
3. check range match or point match;
4. with an empty chamber verify:
   - Flow 500;
   - fan 10,000;
   - CO2_s 400;
   - VPDleaf 1.5;
   - Tleaf 30;
   - light 1500, r90;
5. use a trial leaf to confirm all targets are achievable;
6. open the correct log file;
7. begin the randomized/rotated treatment order.

---

## 14. Procedure for each leaf

1. Confirm treatment, plant, leaf, and time block.
2. Record pre-clamp ambient PPFD, temperature, RH, and light status.
3. Confirm the artificial light is already at target.
4. Open the chamber and place flat interveinal lamina inside.
5. Park, adjust, and close fully.
6. Verify T1 contact.
7. Immediately confirm convergence toward:
   - Tleaf 30 °C;
   - CO2_s 400 μmol mol⁻¹;
   - VPDleaf 1.5 kPa;
   - Qin 1500 μmol m⁻² s⁻¹;
   - correct flow and fan.
8. Start the induction timer.
9. Continue until environmental controls are stable and:
   - Stability is 4/4;
   - A has no sustained trend;
   - gsw is stable enough for the research objective;
   - Tleaf, VPDleaf, and CO2_s are within preregistered tolerances.
10. Tap Log.
11. Complete user constants and remarks.
12. Open the chamber and remove the leaf gently.
13. Inspect for clamp damage.
14. Confirm setpoints recover before the next leaf.

### Suggested project tolerances

Define tolerances before the study, for example:

- Tleaf: setpoint ±0.3 °C;
- CO2_s: setpoint ±5 μmol mol⁻¹;
- VPDleaf: setpoint ±0.1 kPa;
- Qin: setpoint ±1% or the instrument's stable status;
- A and gsw: stability criteria plus no directional drift.

These are project QC suggestions, not universal LI-COR requirements.

---

## 15. Leaf-temperature control requirements

1. TleafCnd must come from T1, not an unintended Energy Balance source.
2. The junction must touch lamina, not a major vein.
3. Reaching Tleaf setpoint does not prove physiological steady state; inspect A and gsw.
4. Stop during dew-point warnings, high RH, condensation, or AutoDry.
5. If the controller reaches its limit, do not relax the temperature for only some leaves. Stop, choose one feasible all-day setpoint and restart, or switch the research question to Scheme A.
6. Retain Tleaf, TleafCnd, TleafEB, Tair, and Txchg for audit.

---

## 16. Required variables

- A, gsw, E, Ci;
- CO2_r, CO2_s;
- H2O_r, H2O_s, RH_s;
- Tleaf, TleafCnd, TleafEB, Tair, Txchg;
- VPDleaf;
- Qin/light-source output;
- flow, ΔP, fan, leak;
- S, K, Geometry;
- exact time, Treatment, Plant_ID, Leaf_ID, Time_Block;
- Induction_Time;
- pre-clamp ambient PPFD, temperature, and RH;
- warning and repeat flags.

Calculate WUE = A/E, iWUE = A/gsw, and Ci/Ca as needed.

---

## 17. Quality-control and exclusion rules

Predefine rules such as:

- no formal data after critical Warmup or Chamber Leak failure;
- exclude or repeat incorrect TleafCnd source or failed thermocouple contact;
- repeat observations outside temperature, CO₂, VPD, or light tolerances;
- repeat records with drifting A or gsw;
- exclude AutoDry, condensation, and high-RH warning periods;
- recompute all records with incorrect leaf area;
- exclude observations altered by an unintended Auto Control/background program;
- flag clamp damage, vein leaks, or visible injury;
- do not compare treatments measured with different stabilization rules.

---

## 18. Troubleshooting

### Slow morning stabilization

A morning leaf may enter 1500 PPFD from low light and require photosynthetic induction and stomatal opening. Extend the wait; do not rely only on 4/4. Pre-induction is possible only when applied identically to all treatments.

### Tleaf cannot reach 30 °C at midday

The target is outside the feasible control range. Before formal work, raise the common setpoint or improve sensor-head shading and ventilation without shading the plant.

### CO2_s unstable

Check cartridge age, soda lime, injector function, flow, leaks, and target variable.

### VPDleaf unavailable

Check humidifier water, desiccant, leaf temperature, dew point, and H₂O setpoint override. Do not log through warnings.

### A stable but gsw still changing

The leaf is not at full gas-exchange steady state. Continue waiting when steady-state stomatal traits are required, or use a preregistered rapid protocol consistently and interpret it accordingly.

### ΔCO₂ too small in stressed leaves

A pilot may justify reducing flow to 300 μmol s⁻¹. Use that flow for every treatment and time and repeat matching and validation.

---

## 19. Data transfer and shutdown

1. Close Log.
2. Wait until the Excel file is fully written.
3. Insert a FAT/FAT32 USB drive.
4. Select `Tools > Manage Files > Copy files to USB`.
5. Copy logs, configuration, and needed diagnostics.
6. Confirm transfer and tap Eject.
7. Tap the power button once and select Shutdown.
8. After power-off, remove and empty the Nafion humidifier column, clean the chamber, and leave it Parked.
9. For long storage, remove the CO₂ cartridge and batteries and follow the official storage guidance.

---

## 20. Data sheet

| Date | Exact time | Treatment | Plant | Leaf | Pre-clamp PPFD | Pre-clamp ambient T | Induction time | A | gsw | E | Ci | CO2_s | TleafCnd | VPDleaf | Qin | Pass QC | Notes |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|

---

## 21. Analysis recommendations

- Use mixed-effects or repeated-measures models when leaves are followed through time.
- Fixed effects: Treatment, Time, Treatment × Time.
- Random effect: Plant_ID/Leaf_ID.
- Even under standardized control, retain actual TleafCnd, VPDleaf, CO2_s, and Qin as QC covariates.
- Scheme A and Scheme B can be analyzed together conceptually:
  - A describes actual environmental performance;
  - B describes potential performance under common conditions;
  - their contrast helps separate environmental limitation from intrinsic leaf-state change.

---

## 22. One-page checklist

### Before startup

- [ ] CO₂ supply, desiccant, humidifier, and soda lime ready
- [ ] Head cable connected while powered Off
- [ ] 6800-12A, 6800-02, aperture, gaskets, and T1 installed
- [ ] Warmup Tests passed
- [ ] Chamber Leak Test passed
- [ ] CO₂ injector functioning

### Settings

- [ ] Complete Gas Exchange; O₂ 21%
- [ ] Broadleaf; correct S; defined K
- [ ] Leaf-temperature source = Measured/T1
- [ ] Flow 500; ΔP 0.1
- [ ] Fan 10,000
- [ ] CO2_s 400
- [ ] VPDleaf 1.5
- [ ] Tleaf 30 °C
- [ ] Light 1500; r90
- [ ] No residual Auto Controls
- [ ] Match/Range Match valid
- [ ] Log file open

### Each leaf

- [ ] Correct sample identity
- [ ] Interveinal lamina fills aperture
- [ ] T1 contacts lamina
- [ ] Tleaf, CO2_s, VPDleaf, and Qin within tolerance
- [ ] A and gsw genuinely stable
- [ ] Induction time recorded
- [ ] No condensation, AutoDry, or warning

### End

- [ ] Close Log and wait for Excel
- [ ] USB copied and ejected
- [ ] Normal Shutdown
- [ ] Humidifier removed
- [ ] Chamber Parked

---

## 23. References

1. User-provided *LI-6800 Quick Start Experimental Guide*, especially the standardized photosynthetic-characteristics protocol, light-response protocol, and appendices.
2. [LI-COR: Assembling the LI-6800](https://www.licor.com/support/LI-6800/topics/assembly.html)
3. [LI-COR: Installing the small leaf chamber](https://www.licor.com/support/LI-6800/topics/chamber-3x3.html)
4. [LI-COR: Preparing for measurements](https://www.licor.com/support/LI-6800/topics/making-leaf-level-measurements.html)
5. [LI-COR: Leaf chamber software controls](https://www.licor.com/support/LI-6800/topics/leaf-measurement-controls.html)
6. [LI-COR: Flow control](https://www.licor.com/support/LI-6800/topics/environment-flow-control.html)
7. [LI-COR: H₂O control](https://www.licor.com/support/LI-6800/topics/environment-h2o-control.html)
8. [LI-COR: Temperature control](https://www.licor.com/support/LI-6800/topics/environment-temperature-control.html)
9. [LI-COR: Light control](https://www.licor.com/support/LI-6800/topics/environment-light-control.html)
10. [LI-COR: Matching the IRGAs](https://www.licor.com/support/LI-6800/topics/matching-the-analyzers.html)
11. [LI-COR: Warmup tests](https://www.licor.com/support/LI-6800/topics/system-tests-warmup.html)
12. [LI-COR: Transferring files](https://www.licor.com/support/LI-6800/topics/file-transfer.html)
13. Echer FR et al. 2015. [Cotton leaf gas exchange responses to irradiance and leaf aging](https://link.springer.com/article/10.1007/s10535-015-0484-3).
14. [Cotton Physiology: Light and the Cotton Plant](https://www.cotton.org/foundation/upload/Stress-Physiology-in-Cotton_Chapter4.pdf).
15. Devi MJ et al. 2018. [Transpiration Response of Cotton to Vapor Pressure Deficit and Its Relationship With Stomatal Traits](https://pmc.ncbi.nlm.nih.gov/articles/PMC6218332/).
