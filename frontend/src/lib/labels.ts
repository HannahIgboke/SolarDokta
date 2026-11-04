// Friendly names for the appliances in the simulator's lists.
const FULL: Record<string, string> = {
  "ac bedroom": "AC (bedroom)", "ac bedrooms": "ACs (bedrooms)", "ac living": "AC (living room)",
  "ac consulting": "AC (consulting room)", "ac principal": "AC (principal's office)",
  "phone laptop": "phone & laptop", "lights 24h": "lights", "borehole pump": "borehole pump",
};
const SHORT: Record<string, string> = {
  "security light": "security", "phone laptop": "laptop", "pumping machine": "pump", "pressing iron": "iron",
  "ac bedroom": "AC", "ac living": "AC", "ac bedrooms": "ACs", "ac consulting": "AC", "ac principal": "AC",
  "washing machine": "washer", "borehole pump": "borehole", "vaccine fridge": "vaccine", "staff fridge": "fridge",
  "computer lab": "comp. lab", "classroom fans": "fans", "lab centrifuge": "centrifuge", "lights 24h": "lights",
  "ward fans": "fans", "home office": "office", "chest freezer": "freezer", "drinks fridge": "fridge",
  "pos and phones": "POS",
};

export const applianceLabel = (name: string) => FULL[name] ?? name;
export const applianceShort = (name: string) => SHORT[name] ?? name.split(" ")[0].slice(0, 9);
