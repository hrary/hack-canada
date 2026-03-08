"""Seed the tariff database with a curated subset of the Canadian Customs Tariff.

Rates are modelled on the real CBSA schedule but simplified for demo purposes.
MFN = Most Favoured Nation (default rate for WTO members).
CUSMA rates apply when rules of origin are met for US/Mexico goods.
Country overrides capture surtaxes (e.g. Canada's 2024-25 surcharges on
certain Chinese imports) and preferential rates under other agreements.
"""

from __future__ import annotations

import sqlite3
import logging

log = logging.getLogger(__name__)

# ── HS code seed data ────────────────────────────────────────────────
# (hs_code, description, mfn_rate, cusma_rate, cusma_eligible)

HS_CODES: list[tuple[str, str, float, float, int]] = [
    # ── Chapter 25-27: Minerals, ores, fuels ─────────────────────────
    ("2501.00", "Salt (including table salt and denatured salt)", 0.0, 0.0, 1),
    ("2504.10", "Natural graphite in powder or flakes", 0.0, 0.0, 1),
    ("2515.11", "Marble, crude or roughly trimmed", 0.0, 0.0, 1),
    ("2516.11", "Granite, crude or roughly trimmed", 0.0, 0.0, 1),
    ("2523.29", "Portland cement, other than white", 0.0, 0.0, 1),
    ("2601.11", "Iron ores and concentrates, non-agglomerated", 0.0, 0.0, 1),
    ("2601.12", "Iron ores and concentrates, agglomerated", 0.0, 0.0, 1),
    ("2602.00", "Manganese ores and concentrates", 0.0, 0.0, 1),
    ("2603.00", "Copper ores and concentrates", 0.0, 0.0, 1),
    ("2604.00", "Nickel ores and concentrates", 0.0, 0.0, 1),
    ("2606.00", "Aluminium ores and concentrates (bauxite)", 0.0, 0.0, 1),
    ("2607.00", "Lead ores and concentrates", 0.0, 0.0, 1),
    ("2608.00", "Zinc ores and concentrates", 0.0, 0.0, 1),
    ("2609.00", "Tin ores and concentrates", 0.0, 0.0, 1),
    ("2610.00", "Chromium ores and concentrates", 0.0, 0.0, 1),
    ("2611.00", "Tungsten ores and concentrates", 0.0, 0.0, 1),
    ("2612.10", "Uranium ores and concentrates", 0.0, 0.0, 1),
    ("2613.10", "Molybdenum ores, roasted", 0.0, 0.0, 1),
    ("2615.10", "Zirconium ores and concentrates", 0.0, 0.0, 1),
    ("2616.10", "Silver ores and concentrates", 0.0, 0.0, 1),
    ("2616.90", "Other precious metal ores", 0.0, 0.0, 1),
    ("2701.12", "Bituminous coal", 0.0, 0.0, 1),
    ("2709.00", "Crude petroleum oils", 0.0, 0.0, 1),
    ("2710.12", "Light petroleum distillates (gasoline)", 0.0, 0.0, 1),
    ("2710.19", "Other petroleum oils (diesel, kerosene)", 0.0, 0.0, 1),
    ("2711.11", "Natural gas, liquefied (LNG)", 0.0, 0.0, 1),
    ("2711.21", "Natural gas, gaseous state", 0.0, 0.0, 1),

    # ── Chapter 28-38: Chemicals ─────────────────────────────────────
    ("2804.29", "Rare gases (neon, argon, krypton)", 3.0, 0.0, 1),
    ("2804.61", "Silicon, containing >= 99.99% Si", 0.0, 0.0, 1),
    ("2811.21", "Carbon dioxide", 3.5, 0.0, 1),
    ("2814.10", "Anhydrous ammonia", 0.0, 0.0, 1),
    ("2825.20", "Lithium oxide and hydroxide", 0.0, 0.0, 1),
    ("2825.60", "Germanium oxides and zirconium dioxide", 3.0, 0.0, 1),
    ("2833.29", "Other sulphates (cobalt, manganese)", 3.5, 0.0, 1),
    ("2836.20", "Disodium carbonate (soda ash)", 3.0, 0.0, 1),
    ("2841.61", "Potassium permanganate", 3.5, 0.0, 1),
    ("2846.10", "Cerium compounds (rare earth)", 0.0, 0.0, 1),
    ("2846.90", "Other rare-earth compounds", 0.0, 0.0, 1),
    ("2850.00", "Hydrides, nitrides, silicides", 3.5, 0.0, 1),
    ("2901.10", "Saturated acyclic hydrocarbons (ethane)", 0.0, 0.0, 1),
    ("2902.20", "Benzene", 0.0, 0.0, 1),
    ("2905.11", "Methanol (methyl alcohol)", 0.0, 0.0, 1),
    ("2917.36", "Terephthalic acid and its salts", 5.5, 0.0, 1),
    ("2933.71", "Caprolactam", 0.0, 0.0, 1),
    ("3002.13", "Blood products for therapeutic use", 0.0, 0.0, 1),
    ("3004.90", "Medicaments, packaged for retail", 0.0, 0.0, 1),
    ("3102.10", "Urea fertiliser", 0.0, 0.0, 1),
    ("3105.20", "Mineral or chemical fertilisers with N, P, K", 0.0, 0.0, 1),
    ("3808.91", "Insecticides, packaged for retail", 6.5, 0.0, 1),
    ("3824.99", "Chemical preparations, not elsewhere specified", 6.5, 0.0, 1),

    # ── Chapter 39: Plastics ─────────────────────────────────────────
    ("3901.10", "Polyethylene, specific gravity < 0.94", 0.0, 0.0, 1),
    ("3901.20", "Polyethylene, specific gravity >= 0.94", 0.0, 0.0, 1),
    ("3902.10", "Polypropylene in primary forms", 0.0, 0.0, 1),
    ("3903.11", "Expandable polystyrene", 6.5, 0.0, 1),
    ("3903.19", "Other polystyrene in primary forms", 6.5, 0.0, 1),
    ("3904.10", "Poly(vinyl chloride), not mixed", 0.0, 0.0, 1),
    ("3907.21", "Methylphosphonate polymer", 6.5, 0.0, 1),
    ("3907.61", "Poly(ethylene terephthalate) — PET", 6.5, 0.0, 1),
    ("3908.10", "Polyamides (nylon) in primary forms", 6.5, 0.0, 1),
    ("3909.10", "Urea resins and thiourea resins", 6.5, 0.0, 1),
    ("3916.20", "Polymer monofilament, rods, sticks (PVC)", 6.5, 0.0, 1),
    ("3917.32", "Plastic tubes and hoses, not reinforced", 6.5, 0.0, 1),
    ("3920.10", "Plates/sheets of polyethylene", 6.5, 0.0, 1),
    ("3921.19", "Cellular plastic plates and sheets", 6.5, 0.0, 1),
    ("3923.30", "Plastic carboys, bottles, flasks", 6.5, 0.0, 1),
    ("3926.90", "Other articles of plastics", 6.5, 0.0, 1),

    # ── Chapter 40: Rubber ───────────────────────────────────────────
    ("4001.22", "Technically specified natural rubber (TSNR)", 0.0, 0.0, 1),
    ("4002.19", "Styrene-butadiene rubber (SBR)", 0.0, 0.0, 1),
    ("4011.10", "New pneumatic tyres for motor cars", 7.0, 0.0, 1),
    ("4011.20", "New pneumatic tyres for trucks/buses", 7.0, 0.0, 1),

    # ── Chapter 44-48: Wood, paper ───────────────────────────────────
    ("4403.11", "Coniferous wood in the rough, treated", 0.0, 0.0, 1),
    ("4407.11", "Coniferous wood, sawn, thickness > 6mm", 0.0, 0.0, 1),
    ("4407.29", "Tropical hardwood, sawn", 0.0, 0.0, 1),
    ("4412.31", "Plywood, with tropical hardwood face", 6.0, 0.0, 1),
    ("4418.20", "Doors and their frames, of wood", 3.5, 0.0, 1),
    ("4801.00", "Newsprint, in rolls or sheets", 0.0, 0.0, 1),
    ("4802.55", "Uncoated paper, 40-150 g/m², in rolls", 0.0, 0.0, 1),
    ("4810.13", "Coated paper, in rolls", 0.0, 0.0, 1),
    ("4819.10", "Cartons, boxes of corrugated paper", 0.0, 0.0, 1),

    # ── Chapter 50-63: Textiles ──────────────────────────────────────
    ("5004.00", "Silk yarn", 0.0, 0.0, 1),
    ("5101.11", "Greasy shorn wool", 0.0, 0.0, 1),
    ("5201.00", "Raw cotton, not carded or combed", 0.0, 0.0, 1),
    ("5205.11", "Cotton yarn, single, uncombed, >= 714 dtex", 0.0, 0.0, 1),
    ("5208.12", "Unbleached plain-weave cotton, 100-200 g/m²", 8.0, 0.0, 1),
    ("5209.42", "Denim cotton fabric, >= 200 g/m²", 12.0, 0.0, 1),
    ("5402.33", "Textured polyester yarn", 8.0, 0.0, 1),
    ("5407.61", "Plain-weave polyester fabric, >= 85%", 14.0, 0.0, 1),
    ("5503.20", "Polyester staple fibres", 6.5, 0.0, 1),
    ("5509.53", "Yarn of polyester mixed with cotton", 8.0, 0.0, 1),
    ("5515.11", "Woven fabric of polyester staple fibres", 14.0, 0.0, 1),
    ("6001.22", "Looped pile knitted cotton fabric", 14.0, 0.0, 1),
    ("6006.32", "Dyed synthetic knitted fabric", 18.0, 0.0, 1),
    ("6104.43", "Women's dresses, knitted, of synthetic", 18.0, 0.0, 1),
    ("6109.10", "T-shirts, singlets, knitted, of cotton", 17.0, 0.0, 1),
    ("6110.20", "Jerseys, pullovers, of cotton", 18.0, 0.0, 1),
    ("6110.30", "Jerseys, pullovers, of man-made fibres", 18.0, 0.0, 1),
    ("6203.42", "Men's trousers, of cotton, not knitted", 17.0, 0.0, 1),
    ("6204.62", "Women's trousers, of cotton, not knitted", 17.0, 0.0, 1),
    ("6302.31", "Bed linen, of cotton", 17.0, 0.0, 1),
    ("6402.91", "Footwear, rubber/plastic, covering ankle", 18.0, 0.0, 1),
    ("6403.91", "Footwear, leather uppers, covering ankle", 18.0, 0.0, 1),
    ("6404.11", "Sports footwear with textile uppers", 18.0, 0.0, 1),

    # ── Chapter 69-70: Ceramics, glass ───────────────────────────────
    ("6902.20", "Refractory bricks, > 50% alumina", 0.0, 0.0, 1),
    ("7003.12", "Non-wired cast/rolled sheet glass, coloured", 0.0, 0.0, 1),
    ("7005.10", "Float glass with non-reflective layer", 3.0, 0.0, 1),
    ("7007.19", "Other tempered safety glass", 3.0, 0.0, 1),
    ("7010.90", "Glass bottles and jars", 0.0, 0.0, 1),
    ("7019.39", "Glass fibre webs, mats, boards", 6.0, 0.0, 1),

    # ── Chapter 72-73: Iron and steel ────────────────────────────────
    ("7201.10", "Non-alloy pig iron, Mn <= 0.5%", 0.0, 0.0, 1),
    ("7203.10", "Ferrous products from direct reduction", 0.0, 0.0, 1),
    ("7206.10", "Iron ingots", 0.0, 0.0, 1),
    ("7207.11", "Semi-finished iron/steel, C < 0.25%, rectangular", 0.0, 0.0, 1),
    ("7207.20", "Semi-finished steel, C >= 0.25%", 0.0, 0.0, 1),
    ("7208.27", "Hot-rolled coil, thickness < 3 mm", 0.0, 0.0, 1),
    ("7208.37", "Hot-rolled sheet, thickness 4.75-10 mm", 0.0, 0.0, 1),
    ("7209.16", "Cold-rolled coil, thickness 1-3 mm", 0.0, 0.0, 1),
    ("7210.49", "Galvanised flat-rolled steel, other", 0.0, 0.0, 1),
    ("7213.10", "Hot-rolled rebar with deformations", 0.0, 0.0, 1),
    ("7214.10", "Forged bars and rods of iron/non-alloy steel", 0.0, 0.0, 1),
    ("7214.20", "Bars and rods with deformations", 0.0, 0.0, 1),
    ("7216.33", "H-sections of iron/non-alloy steel, h >= 80 mm", 0.0, 0.0, 1),
    ("7219.34", "Cold-rolled stainless flat, 0.5-1 mm", 0.0, 0.0, 1),
    ("7222.40", "Stainless steel angles, shapes, sections", 0.0, 0.0, 1),
    ("7225.30", "Hot-rolled alloy steel coil, width >= 600 mm", 0.0, 0.0, 1),
    ("7228.30", "Other alloy steel bars, hot-rolled", 0.0, 0.0, 1),
    ("7304.31", "Cold-drawn seamless steel tubes", 0.0, 0.0, 1),
    ("7306.30", "Other welded steel tubes, circular", 0.0, 0.0, 1),
    ("7308.90", "Iron/steel structures and parts thereof", 0.0, 0.0, 1),
    ("7318.15", "Bolts with nuts, of iron/steel", 6.5, 0.0, 1),
    ("7318.16", "Nuts of iron or steel", 6.5, 0.0, 1),
    ("7326.90", "Other articles of iron or steel", 6.5, 0.0, 1),

    # ── Chapter 74-76: Copper, aluminium ─────────────────────────────
    ("7401.00", "Copper mattes; cement copper", 0.0, 0.0, 1),
    ("7403.11", "Refined copper cathodes", 0.0, 0.0, 1),
    ("7404.00", "Copper waste and scrap", 0.0, 0.0, 1),
    ("7407.10", "Refined copper bars, rods and profiles", 0.0, 0.0, 1),
    ("7408.11", "Refined copper wire, cross-section > 6 mm", 0.0, 0.0, 1),
    ("7409.11", "Refined copper plates, thickness > 0.15 mm", 0.0, 0.0, 1),
    ("7411.10", "Refined copper tubes and pipes", 0.0, 0.0, 1),
    ("7601.10", "Unwrought aluminium, not alloyed", 3.0, 0.0, 1),
    ("7601.20", "Unwrought aluminium alloys", 3.0, 0.0, 1),
    ("7604.10", "Aluminium bars, rods, profiles, not alloyed", 3.0, 0.0, 1),
    ("7606.11", "Aluminium plates/sheets, not alloyed, rectangular", 5.0, 0.0, 1),
    ("7607.11", "Aluminium foil, not backed, rolled", 5.0, 0.0, 1),
    ("7608.10", "Aluminium tubes, not alloyed", 3.0, 0.0, 1),
    ("7610.10", "Aluminium doors, windows, frames", 6.0, 0.0, 1),
    ("7616.99", "Other articles of aluminium", 6.5, 0.0, 1),

    # ── Chapter 78-81: Other base metals ─────────────────────────────
    ("7801.10", "Refined lead, unwrought", 0.0, 0.0, 1),
    ("7901.11", "Zinc, not alloyed, >= 99.99%", 0.0, 0.0, 1),
    ("8001.10", "Tin, not alloyed, unwrought", 0.0, 0.0, 1),
    ("8101.10", "Tungsten powders", 0.0, 0.0, 1),
    ("8103.20", "Unwrought tantalum; tantalum powders", 0.0, 0.0, 1),
    ("8104.11", "Unwrought magnesium, >= 99.8%", 0.0, 0.0, 1),
    ("8108.20", "Unwrought titanium; titanium powders", 0.0, 0.0, 1),
    ("8110.10", "Unwrought antimony; antimony powders", 0.0, 0.0, 1),
    ("8112.12", "Unwrought beryllium", 0.0, 0.0, 1),
    ("8112.21", "Unwrought chromium", 0.0, 0.0, 1),
    ("8112.51", "Unwrought thallium", 0.0, 0.0, 1),
    ("8112.92", "Unwrought niobium (columbium)", 0.0, 0.0, 1),

    # ── Chapter 84: Machinery ────────────────────────────────────────
    ("8401.10", "Nuclear reactors", 0.0, 0.0, 1),
    ("8402.11", "Watertube boilers, steam > 45 t/h", 0.0, 0.0, 1),
    ("8406.82", "Steam turbines, output > 40 MW", 0.0, 0.0, 1),
    ("8407.34", "Spark-ignition engines, > 1000 cc", 2.5, 0.0, 1),
    ("8408.20", "Diesel engines for vehicles", 0.0, 0.0, 1),
    ("8411.12", "Turbojets, thrust <= 25 kN", 0.0, 0.0, 1),
    ("8411.82", "Gas turbines, output > 5000 kW", 0.0, 0.0, 1),
    ("8413.30", "Fuel/lubricant pumps for engines", 0.0, 0.0, 1),
    ("8414.30", "Compressors for refrigeration", 6.0, 0.0, 1),
    ("8414.80", "Other air/gas pumps, compressors", 0.0, 0.0, 1),
    ("8415.10", "Air conditioning machines, wall-mounted", 6.0, 0.0, 1),
    ("8418.10", "Refrigerator-freezer combinations", 8.0, 0.0, 1),
    ("8421.21", "Water filtering/purifying machinery", 0.0, 0.0, 1),
    ("8428.33", "Belt conveyors", 0.0, 0.0, 1),
    ("8429.52", "Excavating machinery, 360° revolving", 0.0, 0.0, 1),
    ("8431.43", "Parts for boring/sinking machinery", 0.0, 0.0, 1),
    ("8443.32", "Printers, capable of connecting to a computer", 0.0, 0.0, 1),
    ("8450.11", "Household washing machines, fully automatic", 8.0, 0.0, 1),
    ("8456.11", "Laser metalworking machine tools", 0.0, 0.0, 1),
    ("8457.10", "Machining centres", 0.0, 0.0, 1),
    ("8458.11", "CNC horizontal lathes for metal", 0.0, 0.0, 1),
    ("8462.21", "CNC bending/folding machines", 0.0, 0.0, 1),
    ("8471.30", "Portable digital computers (laptops)", 0.0, 0.0, 1),
    ("8471.41", "Other digital computers, data processing", 0.0, 0.0, 1),
    ("8471.49", "Digital computers presented as systems", 0.0, 0.0, 1),
    ("8471.70", "Computer storage units", 0.0, 0.0, 1),
    ("8473.30", "Parts of computers and data-processing units", 0.0, 0.0, 1),
    ("8479.89", "Other machines with individual functions", 0.0, 0.0, 1),
    ("8481.80", "Taps, cocks, valves for pipes", 0.0, 0.0, 1),
    ("8482.10", "Ball bearings", 6.5, 0.0, 1),
    ("8483.10", "Transmission shafts and cranks", 0.0, 0.0, 1),
    ("8484.10", "Metallic gaskets and joints", 0.0, 0.0, 1),
    ("8486.20", "Machines for semiconductor fabrication", 0.0, 0.0, 1),
    ("8486.40", "Machines for manufacturing FPDs", 0.0, 0.0, 1),

    # ── Chapter 85: Electrical and electronics ───────────────────────
    ("8501.10", "Electric motors, output <= 37.5 W", 6.0, 0.0, 1),
    ("8501.40", "Single-phase AC motors, output > 0.75 kW", 6.5, 0.0, 1),
    ("8502.13", "Generating sets, diesel, 75-375 kVA", 0.0, 0.0, 1),
    ("8504.40", "Static converters (power supplies, inverters)", 0.0, 0.0, 1),
    ("8506.50", "Lithium primary cells", 0.0, 0.0, 1),
    ("8507.60", "Lithium-ion batteries", 0.0, 0.0, 1),
    ("8517.12", "Smartphones", 0.0, 0.0, 1),
    ("8517.62", "Routers, switches, network equipment", 0.0, 0.0, 1),
    ("8517.70", "Parts of telecom equipment", 0.0, 0.0, 1),
    ("8518.40", "Audio-frequency amplifiers", 6.0, 0.0, 1),
    ("8521.90", "Video recording/reproducing apparatus", 0.0, 0.0, 1),
    ("8523.51", "Semiconductor storage devices (flash)", 0.0, 0.0, 1),
    ("8525.81", "Television cameras, high-definition", 0.0, 0.0, 1),
    ("8528.52", "Monitors, capable of direct connection", 0.0, 0.0, 1),
    ("8529.90", "Parts for monitors, TVs, cameras", 0.0, 0.0, 1),
    ("8532.24", "Multilayer ceramic capacitors", 0.0, 0.0, 1),
    ("8533.21", "Fixed resistors, power <= 20 W", 0.0, 0.0, 1),
    ("8534.00", "Printed circuits (bare PCBs)", 0.0, 0.0, 1),
    ("8536.50", "Switches for <= 1000 V", 3.5, 0.0, 1),
    ("8536.69", "Plugs and sockets for <= 1000 V", 3.5, 0.0, 1),
    ("8537.10", "Control/distribution boards, <= 1000 V", 0.0, 0.0, 1),
    ("8538.90", "Parts for switchgear/control panels", 0.0, 0.0, 1),
    ("8541.10", "Diodes (excl. photosensitive/LED)", 0.0, 0.0, 1),
    ("8541.40", "Photosensitive semiconductor devices (solar cells)", 0.0, 0.0, 1),
    ("8541.41", "LEDs", 0.0, 0.0, 1),
    ("8542.31", "Processors and controllers (ICs)", 0.0, 0.0, 1),
    ("8542.32", "Memory chips (DRAM, NAND)", 0.0, 0.0, 1),
    ("8542.33", "Amplifier ICs", 0.0, 0.0, 1),
    ("8542.39", "Other integrated circuits", 0.0, 0.0, 1),
    ("8542.90", "Parts of integrated circuits", 0.0, 0.0, 1),
    ("8544.42", "Electric conductors, <= 1000 V, with connectors", 3.5, 0.0, 1),
    ("8544.49", "Electric conductors, <= 1000 V, no connectors", 3.0, 0.0, 1),

    # ── Chapter 87: Vehicles ─────────────────────────────────────────
    ("8701.20", "Road tractors for semi-trailers", 6.1, 0.0, 1),
    ("8702.10", "Motor vehicles for >= 10 persons, diesel", 6.1, 0.0, 1),
    ("8703.22", "Motor cars, spark-ignition, 1000-1500 cc", 6.1, 0.0, 1),
    ("8703.23", "Motor cars, spark-ignition, 1500-3000 cc", 6.1, 0.0, 1),
    ("8703.24", "Motor cars, spark-ignition, > 3000 cc", 6.1, 0.0, 1),
    ("8703.32", "Motor cars, diesel, 1500-2500 cc", 6.1, 0.0, 1),
    ("8703.40", "Hybrid electric vehicles, spark-ignition", 6.1, 0.0, 1),
    ("8703.60", "Electric vehicles, battery only", 6.1, 0.0, 1),
    ("8704.21", "Trucks, diesel, GVW <= 5 tonnes", 6.1, 0.0, 1),
    ("8706.00", "Chassis fitted with engines", 6.1, 0.0, 1),
    ("8707.10", "Bodies for passenger vehicles", 6.1, 0.0, 1),
    ("8708.10", "Bumpers and parts thereof", 6.0, 0.0, 1),
    ("8708.21", "Safety seat belts", 6.0, 0.0, 1),
    ("8708.29", "Other body parts and accessories", 6.0, 0.0, 1),
    ("8708.30", "Brakes and servo-brakes, parts thereof", 6.0, 0.0, 1),
    ("8708.40", "Gearboxes and parts thereof", 6.0, 0.0, 1),
    ("8708.50", "Drive axles with differential", 6.0, 0.0, 1),
    ("8708.70", "Road wheels and parts", 6.0, 0.0, 1),
    ("8708.80", "Suspension systems and parts", 6.0, 0.0, 1),
    ("8708.91", "Radiators and parts thereof", 6.0, 0.0, 1),
    ("8708.94", "Steering wheels, columns, gear boxes", 6.0, 0.0, 1),
    ("8708.99", "Other vehicle parts and accessories", 6.0, 0.0, 1),
    ("8711.60", "Electric motorcycles", 0.0, 0.0, 1),
    ("8714.10", "Parts and accessories of motorcycles", 8.0, 0.0, 1),

    # ── Chapter 88: Aircraft ─────────────────────────────────────────
    ("8802.30", "Aeroplanes, unladen weight 2000-15000 kg", 0.0, 0.0, 1),
    ("8802.40", "Aeroplanes, unladen weight > 15000 kg", 0.0, 0.0, 1),
    ("8803.30", "Other parts of aeroplanes/helicopters", 0.0, 0.0, 1),

    # ── Chapter 89: Ships ────────────────────────────────────────────
    ("8901.10", "Cruise ships, excursion boats", 25.0, 0.0, 1),
    ("8901.90", "Other cargo vessels", 25.0, 0.0, 1),
    ("8905.20", "Floating/submersible drilling platforms", 0.0, 0.0, 1),

    # ── Chapter 90: Instruments, sensors ─────────────────────────────
    ("9001.10", "Optical fibres, optical fibre bundles", 0.0, 0.0, 1),
    ("9002.11", "Objective lenses for cameras/projectors", 0.0, 0.0, 1),
    ("9013.80", "Other optical devices and instruments", 0.0, 0.0, 1),
    ("9015.80", "Other surveying instruments", 0.0, 0.0, 1),
    ("9018.90", "Other medical/surgical instruments", 0.0, 0.0, 1),
    ("9022.14", "X-ray apparatus for medical use", 0.0, 0.0, 1),
    ("9026.80", "Other instruments for measuring flow/level", 0.0, 0.0, 1),
    ("9027.80", "Other instruments for physical/chemical analysis", 0.0, 0.0, 1),
    ("9030.33", "Instruments for measuring electricity, with recording", 0.0, 0.0, 1),
    ("9031.41", "Optical instruments for inspecting semiconductors", 0.0, 0.0, 1),
    ("9031.80", "Other measuring or checking instruments", 0.0, 0.0, 1),
    ("9032.89", "Other automatic regulating instruments", 0.0, 0.0, 1),

    # ── Chapter 94: Furniture ────────────────────────────────────────
    ("9401.30", "Swivel seats with adjustable height", 9.5, 0.0, 1),
    ("9401.61", "Upholstered seats, wooden frame", 9.5, 0.0, 1),
    ("9403.20", "Other metal furniture", 9.5, 0.0, 1),
    ("9403.40", "Kitchen furniture of wood", 9.5, 0.0, 1),
    ("9404.21", "Mattresses of cellular rubber", 9.5, 0.0, 1),
    ("9405.11", "Chandeliers for electric lighting", 7.0, 0.0, 1),

    # ── Chapter 95: Toys, games ──────────────────────────────────────
    ("9503.00", "Tricycles, scooters, pedal cars; toys", 8.0, 0.0, 1),
    ("9504.50", "Video game consoles", 0.0, 0.0, 1),

    # ── Chapter 96: Miscellaneous ────────────────────────────────────
    ("9608.10", "Ball-point pens", 7.0, 0.0, 1),
    ("9613.80", "Other lighters", 5.5, 0.0, 1),
    ("9619.00", "Sanitary towels, diapers, tampons", 0.0, 0.0, 1),
]

# ── Country-specific tariff overrides ────────────────────────────────
# (hs_code, country_code, tariff_rate, notes)
#
# Canada imposed a 100% surtax on Chinese EVs (Oct 2024) and 25% surtax
# on Chinese steel/aluminium.  These are additive to MFN.

COUNTRY_OVERRIDES: list[tuple[str, str, float, str]] = [
    # Chinese steel surtax (25% on top of MFN 0%)
    ("7207.11", "CN", 25.0, "25% surtax on Chinese steel (Oct 2024)"),
    ("7207.20", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7208.27", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7208.37", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7209.16", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7210.49", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7213.10", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7214.10", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7214.20", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7216.33", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7219.34", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7222.40", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7225.30", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7228.30", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7304.31", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7306.30", "CN", 25.0, "25% surtax on Chinese steel"),
    ("7308.90", "CN", 25.0, "25% surtax on Chinese steel"),

    # Chinese aluminium surtax (25%)
    ("7601.10", "CN", 28.0, "25% surtax on Chinese aluminium (MFN 3% + 25%)"),
    ("7601.20", "CN", 28.0, "25% surtax on Chinese aluminium"),
    ("7604.10", "CN", 28.0, "25% surtax on Chinese aluminium"),
    ("7606.11", "CN", 30.0, "25% surtax on Chinese aluminium (MFN 5% + 25%)"),
    ("7607.11", "CN", 30.0, "25% surtax on Chinese aluminium"),
    ("7608.10", "CN", 28.0, "25% surtax on Chinese aluminium"),
    ("7610.10", "CN", 31.0, "25% surtax on Chinese aluminium"),
    ("7616.99", "CN", 31.5, "25% surtax on Chinese aluminium"),

    # Chinese EV surtax (100%)
    ("8703.60", "CN", 106.1, "100% surtax on Chinese EVs (MFN 6.1% + 100%)"),
    ("8711.60", "CN", 100.0, "100% surtax on Chinese electric motorcycles"),

    # Chinese solar panel surtax
    ("8541.40", "CN", 25.0, "25% surtax on Chinese solar cells"),

    # Chinese Li-ion battery surtax
    ("8507.60", "CN", 25.0, "25% surtax on Chinese Li-ion batteries"),

    # US Section 232 style — note: CUSMA-eligible goods from US are 0%,
    # but non-originating US steel would get MFN.  We model the 25%
    # retaliatory surtax Canada applied in 2018 (later suspended under CUSMA).
    # Kept here as reference data; lookup logic uses cusma_eligible first.
]


def seed_tariffs(conn: sqlite3.Connection) -> None:
    """Insert seed data into the tariff tables (idempotent)."""
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR IGNORE INTO hs_codes (hs_code, description, mfn_rate, cusma_rate, cusma_eligible) "
        "VALUES (?, ?, ?, ?, ?)",
        HS_CODES,
    )
    cur.executemany(
        "INSERT OR IGNORE INTO country_tariffs (hs_code, country_code, tariff_rate, notes) "
        "VALUES (?, ?, ?, ?)",
        COUNTRY_OVERRIDES,
    )
    conn.commit()
    log.info(
        "Seeded %d HS codes and %d country overrides",
        len(HS_CODES),
        len(COUNTRY_OVERRIDES),
    )
