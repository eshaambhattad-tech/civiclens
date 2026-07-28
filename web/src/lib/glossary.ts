/**
 * Plain-language definitions for the AFR category labels the Illinois
 * Comptroller uses. Keys match `fund_detail` category strings exactly.
 */

export interface GlossaryEntry {
  summary: string;
  includes?: string[];
  note?: string;
}

export const EXPENDITURE_GLOSSARY: Record<string, GlossaryEntry> = {
  "General Government": {
    summary:
      "The cost of running the government itself — administration, record-keeping, and the offices that support every other function.",
    includes: [
      "Salaries for the supervisor, clerk, and assessor",
      "Township hall upkeep, utilities, and insurance",
      "Legal, audit, and accounting fees",
      "Elections administration and public notices",
    ],
    note: "Usually the largest or second-largest line for a township. A high share here relative to program spending is worth asking about.",
  },
  "Social Services": {
    summary:
      "Direct assistance to residents. For Illinois townships this is dominated by General Assistance, a legally mandated program of last resort.",
    includes: [
      "General Assistance cash aid for residents who qualify for no other program",
      "Emergency food, rent, and utility help",
      "Senior services, medical transport, and youth programs",
      "Mental health and substance-use referrals",
    ],
    note: "Townships are required by state law to run General Assistance, which is why nearly every township reports spending here.",
  },
  Transportation: {
    summary:
      "Building and maintaining roads and bridges the township is responsible for — typically unincorporated areas outside city limits.",
    includes: [
      "Road resurfacing, patching, and reconstruction",
      "Snow plowing and salting",
      "Street signs, drainage, and culverts",
      "Highway department equipment and staff",
    ],
    note: "Funded largely through a separate Road & Bridge levy, so it often appears as its own fund.",
  },
  "Culture & Recreation": {
    summary: "Programs and facilities for community life and leisure.",
    includes: ["Recreation programs and community events", "Parks and facility maintenance", "Senior and youth activity centers"],
  },
  "Debt Service": {
    summary: "Payments on money the government has already borrowed — principal plus interest.",
    includes: ["Bond principal repayment", "Interest on bonds and loans", "Debt issuance and paying-agent fees"],
    note: "This is a commitment from past decisions; it cannot be reduced in the current year without refinancing.",
  },
  "Public Safety": {
    summary: "Police, fire, and emergency response functions.",
    includes: ["Police and fire services", "Emergency management", "Building and safety inspection"],
    note: "Rare for townships — most Cook County public safety spending sits with municipalities and the county, not townships.",
  },
  Environment: {
    summary: "Programs protecting land, air, water, and public health conditions.",
    includes: ["Waste and recycling programs", "Stormwater and drainage management", "Open space and conservation"],
  },
  "Control of Environment": {
    summary: "Regulatory and remediation work on environmental conditions.",
    includes: ["Pollution control and monitoring", "Environmental remediation", "Vector and nuisance control"],
  },
  "Community Development": {
    summary: "Investment intended to improve neighborhoods and expand local opportunity.",
    includes: ["Housing assistance and rehabilitation", "Planning and zoning", "Economic development and business support"],
  },
  "Economic & Human Development": {
    summary: "County-level programs combining workforce, housing, and human services investment.",
    includes: ["Workforce training and job placement", "Housing and homelessness programs", "Community grants"],
  },
  "Assessment & Collection of Taxes": {
    summary: "The cost of valuing property and collecting the taxes levied on it.",
    includes: ["Assessor's office operations", "Property valuation and appeals", "Tax billing and collection"],
  },
  "Government Management & Supporting Services": {
    summary: "County-level central administration shared across departments.",
    includes: ["Finance, HR, procurement, and IT", "Facilities management", "Countywide legal services"],
  },
  "Cook County Health & Hospital System": {
    summary:
      "The county's public hospital and clinic network — one of the largest public health systems in the United States.",
    includes: ["Stroger and Provident hospitals", "Community health clinics", "Correctional health services", "CountyCare health plan"],
  },
  Corrections: {
    summary: "Operating the county jail and community supervision programs.",
    includes: ["Cook County Jail operations", "Detainee custody, food, and medical care", "Pretrial and electronic monitoring"],
  },
  Courts: {
    summary: "The court system and the offices that operate around it.",
    includes: ["Circuit Court operations", "Public defender and state's attorney", "Probation and court clerk services"],
  },
  Elections: {
    summary: "Running elections and maintaining voter records.",
    includes: ["Polling places and election judges", "Voting equipment and ballots", "Voter registration and rolls"],
  },
  "Interest & Other Charges": {
    summary: "Interest costs and financing charges not tied to a specific program.",
    includes: ["Interest on outstanding debt", "Fiscal agent and financing fees"],
  },
  Contingencies: {
    summary: "Money set aside for unplanned costs that arise during the year.",
    note: "A budgeted cushion. Large or persistently unspent contingency lines are worth a question.",
  },
  "Non-Programmed Charges": {
    summary: "Costs that do not belong to any single program, held centrally instead.",
    includes: ["Judgments and settlements", "Central insurance and benefit costs"],
  },
  "Public Utility Operations": {
    summary: "Running a utility the government owns, such as water or sewer service.",
    includes: ["Water and sewer operations", "Utility infrastructure maintenance"],
  },
  "Other Expenditures": {
    summary: "Spending the filer did not assign to any listed category.",
    note: "A catch-all. A large amount here reduces how much the filing actually explains — it is a transparency gap, not a program.",
  },
};

export const REVENUE_GLOSSARY: Record<string, GlossaryEntry> = {
  "Property Tax": {
    summary:
      "Taxes on real estate within the government's boundaries — the dominant funding source for Illinois townships.",
    includes: [
      "Levies on residential, commercial, and industrial property",
      "Collected by the county and passed through to each taxing body",
    ],
    note: "Your property tax bill is split across many taxing bodies. The township's share is typically a small slice — schools usually take the largest.",
  },
  "Property Taxes": {
    summary: "Same as Property Tax — taxes levied on real estate within the government's boundaries.",
    note: "Appears under both spellings in Comptroller filings; they mean the same thing.",
  },
  "State Replacement Tax": {
    summary:
      "State money replacing a business property tax that Illinois abolished in 1979. Funded by taxes on corporate income and public utilities.",
    note: "Formally the Personal Property Replacement Tax (PPRT). It rises and falls with the state economy, so it is less predictable than property tax.",
  },
  "Personal Property Replacement Tax": {
    summary: "The formal name for the State Replacement Tax — state funds replacing the abolished personal property tax.",
  },
  "Interest Income": {
    summary: "Earnings on cash the government holds in bank accounts and investments.",
    note: "Rises sharply when interest rates rise, which can make year-over-year revenue look better without any policy change.",
  },
  "Investment Income": {
    summary: "Returns on the government's invested reserves and portfolio holdings.",
  },
  "Charges for Services": {
    summary: "Fees paid by the people who directly use a specific service.",
    includes: ["Program and activity fees", "Permit and inspection fees", "Facility rentals"],
  },
  "Licenses, Fees & Charges for Services": {
    summary: "Combined revenue from licensing, permitting, and user fees.",
  },
  "Licenses & Permits": {
    summary: "Payments for permission to operate, build, or conduct a regulated activity.",
    includes: ["Business and liquor licenses", "Building permits", "Animal and vehicle licensing"],
  },
  "Other Intergovernmental": {
    summary: "Money received from other units of government — state, federal, county, or municipal.",
    note: "Often grant pass-throughs. It can appear and disappear year to year as specific grants start and end.",
  },
  "Operating Grants & Contributions": {
    summary: "Grant money restricted to running specific programs rather than building things.",
  },
  "Capital Grants & Contributions": {
    summary: "Grant money restricted to building or buying long-lived assets.",
    includes: ["Road and facility construction grants", "Equipment and vehicle grants"],
  },
  "Federal Sources": { summary: "Funds received directly from federal agencies or federal programs." },
  "Other State Sources": { summary: "State funds outside the main shared-tax formulas, typically program-specific." },
  "State Income Tax": {
    summary: "Each local government's share of Illinois income tax, distributed by population through the Local Government Distributive Fund.",
  },
  "State Motor Fuel Tax": {
    summary: "A share of state fuel taxes, restricted by law to road and transportation purposes.",
  },
  "Gasoline Tax": { summary: "Local tax on motor fuel sales." },
  "County Sales Tax": { summary: "The county's share of sales tax on goods sold within its boundaries." },
  "County Use Tax": { summary: "Tax on goods bought outside the county but used within it." },
  "Cigarette Tax": { summary: "Excise tax on tobacco sales." },
  "Alcoholic Beverage Tax": { summary: "Excise tax on alcohol sales." },
  "Cannabis Tax": { summary: "Tax on legal cannabis sales, a revenue source only since Illinois legalization in 2020." },
  "Amusement Tax": { summary: "Tax on admissions to entertainment — concerts, sporting events, and venues." },
  "Hotel Accommodations Tax": { summary: "Tax on short-term lodging, largely paid by visitors rather than residents." },
  "Parking Lot & Garage Operations Tax": { summary: "Tax on paid parking transactions." },
  "Illinois Gaming Tax": { summary: "The local share of state gambling revenue from casinos and gaming positions." },
  "Sports Wagering Tax": { summary: "Tax on legal sports betting, a recent addition to Illinois revenue." },
  "Other Taxes": { summary: "Tax revenue the filer did not break out into a named category." },
  "Fines & Forfeitures": {
    summary: "Money from penalties — court fines, ordinance violations, and forfeited property.",
  },
  "Miscellaneous Revenue": {
    summary: "Income that fits no other category.",
    note: "A catch-all line; a large amount here limits how much the filing explains.",
  },
  "Other Revenue": {
    summary: "Revenue the filer did not assign to a listed category.",
    note: "A catch-all line; a large amount here limits how much the filing explains.",
  },
};

export function lookupCategory(name: string, kind: "expenditure" | "revenue") {
  const table = kind === "expenditure" ? EXPENDITURE_GLOSSARY : REVENUE_GLOSSARY;
  return table[name] ?? null;
}
