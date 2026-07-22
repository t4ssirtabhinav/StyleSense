// Static option lists for SS-004's onboarding wizard. Per
// docs/tickets/SS-004-design.md's "Files to create/modify" #5
// (2026-07-13 revision, scope narrowed).
//
// Only the genuinely-static pieces live here — gender/wardrobe_type/
// budget_range are called out by the ticket's Technical Note as
// "structurally stable". STYLE_KEYWORDS / OCCASION_PRIORITY_OPTIONS /
// PLACEHOLDER_COLOUR_PALETTE are NOT here — they are DB-backed reference
// tables fetched via onboarding.taxonomies.service.ts.
import type {
  BudgetRangeKey,
  GenderKey,
  IndianCity,
  WardrobeTypeKey,
} from './onboarding.types';

export interface GenderOption {
  key: GenderKey;
  label: string;
}

export const GENDER_OPTIONS: GenderOption[] = [
  { key: 'woman', label: 'Woman' },
  { key: 'man', label: 'Man' },
  { key: 'non_binary', label: 'Non-binary' },
  { key: 'prefer_not_to_say', label: 'Prefer not to say' },
];

export interface WardrobeTypeOption {
  key: WardrobeTypeKey;
  label: string;
}

export const WARDROBE_TYPES: WardrobeTypeOption[] = [
  { key: 'mostly_western', label: 'Mostly Western' },
  { key: 'mostly_ethnic', label: 'Mostly Ethnic' },
  { key: 'equal_mix', label: 'Equal Mix' },
  { key: 'mostly_formal', label: 'Mostly Formal' },
  { key: 'mostly_casual', label: 'Mostly Casual' },
];

export interface BudgetRangeOption {
  key: BudgetRangeKey;
  label: string;
}

export const BUDGET_RANGES: BudgetRangeOption[] = [
  { key: '500_1000', label: '₹500–1k' },
  { key: '1000_3000', label: '₹1k–3k' },
  { key: '3000_10000', label: '₹3k–10k' },
  { key: '10000_plus', label: '₹10k+' },
];

// Ranked by population/metro size — see docs/tickets/SS-004-design.md's
// "Concrete values" section for the full reasoning (this is genuinely new
// app data, not a design token/schema/API contract).
export const TOP_50_INDIAN_CITIES: IndianCity[] = [
  {
    id: 'mumbai',
    name: 'Mumbai',
    state: 'Maharashtra',
    lat: 19.076,
    lng: 72.8777,
  },
  { id: 'delhi', name: 'Delhi', state: 'Delhi', lat: 28.7041, lng: 77.1025 },
  {
    id: 'bengaluru',
    name: 'Bengaluru',
    state: 'Karnataka',
    lat: 12.9716,
    lng: 77.5946,
  },
  {
    id: 'hyderabad',
    name: 'Hyderabad',
    state: 'Telangana',
    lat: 17.385,
    lng: 78.4867,
  },
  {
    id: 'ahmedabad',
    name: 'Ahmedabad',
    state: 'Gujarat',
    lat: 23.0225,
    lng: 72.5714,
  },
  {
    id: 'chennai',
    name: 'Chennai',
    state: 'Tamil Nadu',
    lat: 13.0827,
    lng: 80.2707,
  },
  {
    id: 'kolkata',
    name: 'Kolkata',
    state: 'West Bengal',
    lat: 22.5726,
    lng: 88.3639,
  },
  { id: 'surat', name: 'Surat', state: 'Gujarat', lat: 21.1702, lng: 72.8311 },
  {
    id: 'pune',
    name: 'Pune',
    state: 'Maharashtra',
    lat: 18.5204,
    lng: 73.8567,
  },
  {
    id: 'jaipur',
    name: 'Jaipur',
    state: 'Rajasthan',
    lat: 26.9124,
    lng: 75.7873,
  },
  {
    id: 'lucknow',
    name: 'Lucknow',
    state: 'Uttar Pradesh',
    lat: 26.8467,
    lng: 80.9462,
  },
  {
    id: 'kanpur',
    name: 'Kanpur',
    state: 'Uttar Pradesh',
    lat: 26.4499,
    lng: 80.3319,
  },
  {
    id: 'nagpur',
    name: 'Nagpur',
    state: 'Maharashtra',
    lat: 21.1458,
    lng: 79.0882,
  },
  {
    id: 'indore',
    name: 'Indore',
    state: 'Madhya Pradesh',
    lat: 22.7196,
    lng: 75.8577,
  },
  {
    id: 'thane',
    name: 'Thane',
    state: 'Maharashtra',
    lat: 19.2183,
    lng: 72.9781,
  },
  {
    id: 'bhopal',
    name: 'Bhopal',
    state: 'Madhya Pradesh',
    lat: 23.2599,
    lng: 77.4126,
  },
  {
    id: 'visakhapatnam',
    name: 'Visakhapatnam',
    state: 'Andhra Pradesh',
    lat: 17.6868,
    lng: 83.2185,
  },
  {
    id: 'pimpri_chinchwad',
    name: 'Pimpri-Chinchwad',
    state: 'Maharashtra',
    lat: 18.6298,
    lng: 73.7997,
  },
  { id: 'patna', name: 'Patna', state: 'Bihar', lat: 25.5941, lng: 85.1376 },
  {
    id: 'vadodara',
    name: 'Vadodara',
    state: 'Gujarat',
    lat: 22.3072,
    lng: 73.1812,
  },
  {
    id: 'ghaziabad',
    name: 'Ghaziabad',
    state: 'Uttar Pradesh',
    lat: 28.6692,
    lng: 77.4538,
  },
  {
    id: 'ludhiana',
    name: 'Ludhiana',
    state: 'Punjab',
    lat: 30.901,
    lng: 75.8573,
  },
  {
    id: 'agra',
    name: 'Agra',
    state: 'Uttar Pradesh',
    lat: 27.1767,
    lng: 78.0081,
  },
  {
    id: 'nashik',
    name: 'Nashik',
    state: 'Maharashtra',
    lat: 19.9975,
    lng: 73.7898,
  },
  {
    id: 'faridabad',
    name: 'Faridabad',
    state: 'Haryana',
    lat: 28.4089,
    lng: 77.3178,
  },
  {
    id: 'meerut',
    name: 'Meerut',
    state: 'Uttar Pradesh',
    lat: 28.9845,
    lng: 77.7064,
  },
  {
    id: 'rajkot',
    name: 'Rajkot',
    state: 'Gujarat',
    lat: 22.3039,
    lng: 70.8022,
  },
  {
    id: 'kalyan_dombivli',
    name: 'Kalyan-Dombivli',
    state: 'Maharashtra',
    lat: 19.2403,
    lng: 73.1305,
  },
  {
    id: 'vasai_virar',
    name: 'Vasai-Virar',
    state: 'Maharashtra',
    lat: 19.4912,
    lng: 72.8054,
  },
  {
    id: 'varanasi',
    name: 'Varanasi',
    state: 'Uttar Pradesh',
    lat: 25.3176,
    lng: 82.9739,
  },
  {
    id: 'srinagar',
    name: 'Srinagar',
    state: 'Jammu & Kashmir',
    lat: 34.0837,
    lng: 74.7973,
  },
  {
    id: 'aurangabad',
    name: 'Aurangabad',
    state: 'Maharashtra',
    lat: 19.8762,
    lng: 75.3433,
  },
  {
    id: 'dhanbad',
    name: 'Dhanbad',
    state: 'Jharkhand',
    lat: 23.7957,
    lng: 86.4304,
  },
  {
    id: 'amritsar',
    name: 'Amritsar',
    state: 'Punjab',
    lat: 31.634,
    lng: 74.8723,
  },
  {
    id: 'navi_mumbai',
    name: 'Navi Mumbai',
    state: 'Maharashtra',
    lat: 19.033,
    lng: 73.0297,
  },
  {
    id: 'prayagraj',
    name: 'Prayagraj',
    state: 'Uttar Pradesh',
    lat: 25.4358,
    lng: 81.8463,
  },
  {
    id: 'ranchi',
    name: 'Ranchi',
    state: 'Jharkhand',
    lat: 23.3441,
    lng: 85.3096,
  },
  {
    id: 'howrah',
    name: 'Howrah',
    state: 'West Bengal',
    lat: 22.5958,
    lng: 88.2636,
  },
  {
    id: 'coimbatore',
    name: 'Coimbatore',
    state: 'Tamil Nadu',
    lat: 11.0168,
    lng: 76.9558,
  },
  {
    id: 'jabalpur',
    name: 'Jabalpur',
    state: 'Madhya Pradesh',
    lat: 23.1815,
    lng: 79.9864,
  },
  {
    id: 'gwalior',
    name: 'Gwalior',
    state: 'Madhya Pradesh',
    lat: 26.2183,
    lng: 78.1828,
  },
  {
    id: 'vijayawada',
    name: 'Vijayawada',
    state: 'Andhra Pradesh',
    lat: 16.5062,
    lng: 80.648,
  },
  {
    id: 'jodhpur',
    name: 'Jodhpur',
    state: 'Rajasthan',
    lat: 26.2389,
    lng: 73.0243,
  },
  {
    id: 'madurai',
    name: 'Madurai',
    state: 'Tamil Nadu',
    lat: 9.9252,
    lng: 78.1198,
  },
  {
    id: 'raipur',
    name: 'Raipur',
    state: 'Chhattisgarh',
    lat: 21.2514,
    lng: 81.6296,
  },
  { id: 'kota', name: 'Kota', state: 'Rajasthan', lat: 25.2138, lng: 75.8648 },
  {
    id: 'guwahati',
    name: 'Guwahati',
    state: 'Assam',
    lat: 26.1445,
    lng: 91.7362,
  },
  {
    id: 'chandigarh',
    name: 'Chandigarh',
    state: 'Chandigarh',
    lat: 30.7333,
    lng: 76.7794,
  },
  {
    id: 'thiruvananthapuram',
    name: 'Thiruvananthapuram',
    state: 'Kerala',
    lat: 8.5241,
    lng: 76.9366,
  },
  {
    id: 'bhubaneswar',
    name: 'Bhubaneswar',
    state: 'Odisha',
    lat: 20.2961,
    lng: 85.8245,
  },
];
