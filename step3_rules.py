from __future__ import annotations

COMPETITOR_PATTERNS = [
    "bidprime.com", "highergov.com", "govtribe.com", "mygovwatch.com", "bidbanana.thebidlab.com",
    "j360.info", "findrfp.com", "govcb.com", "instantmarkets.com", "rfpdb.com",
    "alabamabids.com", "alaskabids.com", "arizonabids.com", "arkansasbids.com", "californiabids.com",
    "coloradobids.com", "connecticutbids.com", "delawarebids.com", "floridabids.com", "georgiabids.com",
    "hawaiibids.com", "idahobids.com", "illinoisbids.com", "indianabids.com", "iowabids.com", "kansasbids.com",
    "kentuckybids.com", "louisianabids.com", "mainebids.com", "marylandbids.com", "massachusettsbids.com",
    "michiganbids.com", "minnesotabids.com", "mississippibids.com", "missouribids.com", "montanabids.com",
    "nebraskabids.com", "nevadabids.com", "newhampshirebids.com", "newjerseybids.com", "newmexicobids.com",
    "newyorkbids.com", "northcarolinabids.com", "northdakotabids.com", "ohiobids.com", "oklahomabids.com",
    "oregonbids.com", "pennsylvaniabids.com", "rhodeislandbids.com", "southcarolinabids.com", "southdakotabids.com",
    "tennesseebids.com", "texasbids.com", "utahbids.com", "vermontbids.com", "virginiabids.com", "washingtonbids.com",
    "westvirginiabids.com", "wisconsinbids.com", "wyomingbids.com", "constructionbidsource.com", "globaltenders.com",
    "constructionwork.com", "governmentcontracts.us",
]

IRRELEVANT_PATTERNS = [
    "youtube.com", "bidcal.com", "catawiki.com", "heritageauctions.com", "hibid.com", "liveauctioneers.com",
    "proxibid.com", "auctionzip.com", "govdeals.com", "publicsurplus.com", "bidspotter.com", "bidfta.com",
    "bidorbuy.co.za", "allsurplus.com", "godaddy.com", "auctions.godaddy.com", "sedo.com", "namejet.com",
    "snapnames.com", "afternic.com", "dan.com", "flippa.com", "sav.com", "dynadot.com", "namecheap.com",
    "dealdash.com", "quidco.com", "bobshop.co.za", "govplanet.com", "ironplanet.com", "rbauction.com",
    "youtu.be", "facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com", "tiktok.com",
    "linkedin.com", "constantcontact.com",
]

THIRD_PARTY_PATTERNS = [
    "jaggaer.com", "publicpurchase.com", "procureware.com", "planetbids.com", "opengov.com", "negometrix.com",
    "ionwave.net", "internationaleprocurement.com", "inforcloudsuite.com", "demandstar.com", "civicplus.com",
    "bonfirehub.com", "bidx.com", "bidsandtenders.net", "bidnetdirect.com", "bidexpress.com", "beaconbid.com",
    "vendorregistry.com", "govspend.com", "iq.govwin.com", "myvendorlink.com", "vendorlink", "pennbid.net",
    "centralauctionhouse.com",
]

OFFICIAL_PATTERNS = [
    "sam.gov", "purchasing.alabama.gov", "aws.state.ak.us", "app.az.gov", "transform.ar.gov", "caleprocure.ca.gov",
    "colorado.gov/vss", "biznet.ct.gov", "bids.delaware.gov", "vendor.myfloridamarketplace.com", "team.georgia.gov",
    "hands.ehawaii.gov", "purchasing.idaho.gov", "bidbuy.illinois.gov", "in.gov", "bidopportunities.iowa.gov",
    "admin.ks.gov", "vss.ky.gov", "doa.louisiana.gov", "maine.gov", "emma.maryland.gov", "commbuys.com",
    "sigma.michigan.gov", "mn.gov", "dfa.ms.gov", "mo.gov", "svc.mt.gov", "das.nebraska.gov", "nevadasbdc.org",
    "das.nh.gov", "njstart.gov", "generalservices.state.nm.us", "nyscr.ny.gov", "eprocurement.nc.gov", "nd.gov",
    "procure.ohio.gov", "omes.ok.gov", "oregon.gov", "emarketplace.state.pa.us", "purchasing.ri.gov",
    "procurement.sc.gov", "boa.sd.gov", "tn.gov", "esbd.cpa.state.tx.us", "bidsync.com", "bgs.vermont.gov",
    "eva.virginia.gov", "des.wa.gov", "purchasing.wv.gov", "vendornet.wi.gov", "ai.wyo.gov",
]

CONSTRUCTION_PATTERNS = [
    "construction.com", "buildcentral.com", "constructconnect.com", "cmdgroup.com", "smartbid.co",
    "buildingconnected.com", "isqft.com", "planhub.com", "civcastusa.com", "questcdn.com", "esri.com",
]

FILE_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip")

URL_REJECT_TERMS_GROUPS = [
    ["agenda", "minutes", "board packet", "resolution", "ordinance"],
    ["news", "press", "blog", "article", "announcement"],
    ["policy", "manual", "handbook", "guide", "guidelines", "instructions"],
    ["jobs", "careers", "employment", "permits", "licensing", "tax", "utility payment", "parking ticket", "admissions"],
    ["login", "sign in", "signin", "register", "registration", "dashboard", "profile", "reset password", "forgot password", "sso", "authenticate", "auction"],
]

HIGH_INTENT_URL_PASS_TERMS = [
    "opportunities", "opportunity", "solicitations", "solicitation", "procurement", "eprocurement", "list",
    "bid", "bids", "contracts", "contract", "contracting", "awards", "award", "rfp", "rfps", "rfq", "rfqs", "ifb", "itb", "page",
]

HIGH_INTENT_TITLE_PASS_TERMS = [
    "request for proposal", "open bids", "open solicitations", "rfps", "bids", "rfqs",
]

GENERAL_TITLE_REJECT_TERMS_GROUPS = URL_REJECT_TERMS_GROUPS

GENERAL_TITLE_DESC_REJECT_TERMS = ["how", "win"]

GENERAL_TITLE_PASS_TERMS = [
    "opportunities", "opportunity", "solicitations", "solicitation", "procurement", "eprocurement", "bids",
    "contracts", "contracting", "awards", "rfp", "rfps", "rfq", "rfqs", "ifb", "itb",
]

GENERAL_TITLE_REVIEW_ONLY_TERMS = ["list", "bid", "contract", "award"]

TYPE_ENUM = {
    "competitor",
    "irrelevant",
    "third_party_platform",
    "official_platform",
    "construction_platform",
    "other",
}
