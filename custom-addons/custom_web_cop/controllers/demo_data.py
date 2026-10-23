"""Demo/dummy data for the customer portal during development.

Easily replaced later with real project.project / fleet.vehicle /
account.move records — the controller builds its row dicts from here.
"""
import datetime

TODAY = datetime.date(2026, 10, 7)

PROJECT_STATUSES = [
    "Draft", "New", "In Progress", "On Hold",
    "Completed", "Cancelled", "Pending", "Approved",
]

PROJECT_STATUS_STYLES = {
    "Draft":      "background: #F3F4F6; color: #6B7280;",
    "New":        "background: #EFF6FF; color: #3B82F6;",
    "In Progress":"background: #FFF7ED; color: #F97316;",
    "On Hold":    "background: #FEF3C7; color: #D97706;",
    "Completed":  "background: #ECFDF5; color: #00A85A;",
    "Cancelled":  "background: #FEF2F2; color: #DC2626;",
    "Pending":    "background: #F3E8FF; color: #8B5CF6;",
    "Approved":   "background: #ECFDF5; color: #059669;",
}

def d(days):
    return TODAY + datetime.timedelta(days=days)

PROJECTS = [
    # (name, ref, status, start, end, description)
    ("Toyota Land Cruiser Fleet Upgrade",   "PRJ-2026-001", "In Progress", d(-120), d(60),  "Upgrade of 5 Land Cruisers with telemetry units."),
    ("Dar es Salaam Warehouse Racking",     "PRJ-2026-002", "Completed",   d(-300), d(-30), "Installation of pallet racking systems."),
    ("Isuzu Truck Maintenance Cycle Q1",    "PRJ-2026-003", "New",         d(3),    d(90),  "Quarterly preventive maintenance for trucks."),
    ("GPS Tracking Rollout Phase II",       "PRJ-2026-004", "Approved",    d(7),    d(120), "Fitment of GPS trackers across the fleet."),
    ("Office Relocation Mikocheni",         "PRJ-2026-005", "Draft",       None,    None,   "Planning stage for new office space."),
    ("Cold Chain Vehicle Conversion",       "PRJ-2026-006", "In Progress", d(-60),  d(45),  "Converting 3 vans to refrigerated units."),
    ("Driver Training Program 2026",        "PRJ-2026-007", "Pending",     d(14),   d(75),  "Defensive driving certification for drivers."),
    ("Fleet Insurance Renewal",             "PRJ-2026-008", "On Hold",     d(-20),  d(40),  "Awaiting underwriter confirmation."),
    ("Arusha Route Optimization",           "PRJ-2026-009", "Completed",   d(-200), d(-80), "Route planning software deployment."),
    ("Hybrid Vehicle Pilot",                "PRJ-2026-010", "New",         d(10),   d(150), "Pilot program for hybrid delivery vehicles."),
    ("Tire Supply Framework Agreement",     "PRJ-2026-011", "Approved",    d(-5),   d(365), "Annual tire supply contract."),
    ("Fuel Card System Migration",          "PRJ-2026-012", "In Progress", d(-45),  d(30),  "Migration to a new fuel card provider."),
    ("Mwanza Depot Setup",                  "PRJ-2026-013", "Draft",       None,    None,   "New depot feasibility study."),
    ("Vehicle Branding Refresh",            "PRJ-2026-014", "Pending",     d(21),   d(60),  "Rebranding of 12 vehicles."),
    ("Telematics Data Integration",         "PRJ-2026-015", "Cancelled",   d(-90),  d(-10), "Superseded by GPS Tracking Phase II."),
    ("Safety Compliance Audit",             "PRJ-2026-016", "In Progress", d(-15),  d(20),  "Fleet safety standards audit."),
    ("Spare Parts Inventory Overhaul",      "PRJ-2026-017", "New",         d(5),    d(110), "Warehouse management for spares."),
    ("Dodoma Fleet Expansion",              "PRJ-2026-018", "Approved",    d(30),   d(200), "Purchase and registration of 8 trucks."),
    ("Emissions Testing Program",           "PRJ-2026-019", "Completed",   d(-250), d(-150),"Annual emissions certification."),
    ("Recovery Vehicle Procurement",        "PRJ-2026-020", "On Hold",     d(-35),  d(50),  "Pending budget approval."),
    ("Night Dispatch Software",             "PRJ-2026-021", "In Progress", d(-70),  d(25),  "Dispatch scheduling platform."),
    ("Border Compliance Documentation",     "PRJ-2026-022", "Pending",     d(45),   d(90),  "Cross-border transport permits."),
]

VEHICLES = [
    # (plate, model, status, odometer, assigned_to)
    ("T 123 ABC", "Toyota Land Cruiser V8",  "Active",    148_230, "Juma Mwakyusa"),
    ("T 456 DEF", "Isuzu FRR 900",           "Active",     92_410, "Asha Kilonzo"),
    ("T 789 GHI", "Toyota Hiace",            "Maintenance", 61_880, None),
    ("T 234 JKL", "Mitsubishi Fuso Canter",  "Active",    203_500, "Neema Mrisho"),
    ("T 567 MNO", "Nissan UD Truck",         "Active",    176_020, "Baraka Mtenga"),
    ("T 890 PQR", "Toyota Land Cruiser TX",  "Idle",       44_600, None),
    ("T 123 STU", "Suzuki Every",            "Active",     28_940, "Fatma Suleiman"),
    ("T 456 VWX", "Isuzu NPR",               "Retired",   310_000, None),
    ("T 789 YZA", "Mazda BT-50",             "Active",     87_150, "Omari Nyerere"),
    ("T 234 BCD", "Toyota Coaster",          "Maintenance",119_730, None),
    ("T 567 EFG", "Hino 500",                "Active",    134_290, "Zainab Kessy"),
    ("T 890 HIJ", "Ford Ranger",             "Active",     55_410, "Salim Macho"),
    ("T 123 KLM", "Toyota Vitz",             "Idle",       19_800, None),
    ("T 456 NOP", "Scania R450",             "Active",    421_650, "Hamisi Juma"),
    ("T 789 QRS", "Toyota Dyna",             "Active",     98_340, "Grace Mwakalinga"),
    ("T 234 TUV", "Mercedes Actros",         "Maintenance",265_900, None),
    ("T 567 WXY", "Nissan Patrol",           "Active",     71_220, "Peter Msigwa"),
    ("T 890 ZAB", "Toyota Corolla",          "Retired",   240_110, None),
    ("T 123 CDE", "Volkswagen Amarok",       "Active",     63_470, "Rehema Said"),
    ("T 456 FGH", "Toyota Hilux",            "Active",     84_960, "Daniel Chuwa"),
]

INVOICE_STATUSES = [
    "Draft", "Posted", "Paid", "Partially Paid", "Overdue", "Cancelled",
]

INVOICE_STATUS_STYLES = {
    "Draft":          "background: #F3F4F6; color: #6B7280;",
    "Posted":         "background: #EFF6FF; color: #3B82F6;",
    "Paid":           "background: #ECFDF5; color: #00A85A;",
    "Partially Paid": "background: #FFF7ED; color: #F97316;",
    "Overdue":        "background: #FEF2F2; color: #DC2626;",
    "Cancelled":      "background: #F3F4F6; color: #9CA3AF;",
}

# (number, date, due, status, description, total, paid)
INVOICES = [
    ("INV/2026/00001", d(-180), d(-150), "Paid",           "Fleet maintenance services — Q1",      4_500_000, 4_500_000),
    ("INV/2026/00002", d(-170), d(-140), "Paid",           "GPS tracking subscription",             1_200_000, 1_200_000),
    ("INV/2026/00003", d(-160), d(-130), "Partially Paid", "Tire supply — 40 units",               8_800_000, 4_000_000),
    ("INV/2026/00004", d(-150), d(-120), "Paid",           "Vehicle branding refresh",              3_300_000, 3_300_000),
    ("INV/2026/00005", d(-140), d(-110), "Overdue",        "Warehouse racking installation",       12_500_000, 0),
    ("INV/2026/00006", d(-130), d(-100), "Paid",           "Driver training program",               2_750_000, 2_750_000),
    ("INV/2026/00007", d(-120), d(-90),  "Cancelled",      "Cold chain conversion (re-booked)",     9_000_000, 0),
    ("INV/2026/00008", d(-110), d(-80),  "Paid",           "Insurance premium — annual",            6_400_000, 6_400_000),
    ("INV/2026/00009", d(-100), d(-70),  "Partially Paid", "Fuel card top-ups — September",        15_700_000, 7_000_000),
    ("INV/2026/00010", d(-90),  d(-60),  "Paid",           "Route optimization license",            1_850_000, 1_850_000),
    ("INV/2026/00011", d(-80),  d(-50),  "Overdue",        "Spare parts supply",                    5_250_000, 0),
    ("INV/2026/00012", d(-70),  d(-40),  "Paid",           "Emissions testing — fleet",             980_000,   980_000),
    ("INV/2026/00013", d(-60),  d(-30),  "Paid",           "Telematics data integration",           2_100_000, 2_100_000),
    ("INV/2026/00014", d(-50),  d(-20),  "Partially Paid", "Hybrid vehicle pilot deposit",         11_000_000, 5_500_000),
    ("INV/2026/00015", d(-40),  d(-10),  "Paid",           "Night dispatch software setup",         3_600_000, 3_600_000),
    ("INV/2026/00016", d(-30),  d(-2),   "Overdue",        "Recovery vehicle deposit",              7_200_000, 0),
    ("INV/2026/00017", d(-20),  d(10),   "Posted",         "Fleet maintenance services — Q4",      4_850_000, 0),
    ("INV/2026/00018", d(-10),  d(20),   "Posted",         "Tire supply — November batch",          6_300_000, 0),
    ("INV/2026/00019", d(-5),   d(25),   "Draft",          "Border compliance documentation",       1_450_000, 0),
    ("INV/2026/00020", d(-1),   d(29),   "Draft",          "Dodoma fleet expansion — advance",     18_900_000, 0),
    ("INV/2026/00021", d(0),    d(30),   "Posted",         "Fuel card top-ups — October",          14_200_000, 0),
]
