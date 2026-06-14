// src/lib/epn.ts
const MARKET_TO_TLD_AND_MKRID: Record<string, { tld: string; mkrid: string }> = {
  US: { tld: "com", mkrid: "711-53200-19255-0" },
  CA: { tld: "ca",  mkrid: "706-53473-19255-0" },
  GB: { tld: "co.uk", mkrid: "710-53481-19255-0" },
  DE: { tld: "de",  mkrid: "707-53477-19255-0" },
  FR: { tld: "fr",  mkrid: "709-53476-19255-0" },
  AU: { tld: "com.au", mkrid: "705-53470-19255-0" },
  // add more from the official table as needed
};

const MARKET = (import.meta.env.VITE_EPN_MARKET || "US").toUpperCase();
const { tld, mkrid } = MARKET_TO_TLD_AND_MKRID[MARKET] || MARKET_TO_TLD_AND_MKRID.US;

const CAMPID = import.meta.env.VITE_EPN_CAMPAIGN_ID || "";
const CUSTOMID = import.meta.env.VITE_EPN_CUSTOM_ID || "";
const TOOLID = "10001"; // default tool id per docs

// Append EPN params to any eBay target URL (item, search, category)
export function epnAffiliateUrl(targetUrl: string): string {
  const u = new URL(targetUrl);
  // Required params (click=1, channel=EPN=1, rotation id=market, campaign id, tool id)
  u.searchParams.set("mkevt", "1");          // click
  u.searchParams.set("mkcid", "1");          // EPN channel
  u.searchParams.set("mkrid", mkrid);        // rotation id for marketplace
  if (CAMPID) u.searchParams.set("campid", CAMPID);
  u.searchParams.set("toolid", TOOLID);
  if (CUSTOMID) u.searchParams.set("customid", CUSTOMID);
  return u.toString();
}

// Build a search target URL for a query, then affiliate-ize it.
export function epnSearchUrl(q: string): string {
  const target = `https://www.ebay.${tld}/sch/i.html?_nkw=${encodeURIComponent(q)}`;
  return epnAffiliateUrl(target);
}
