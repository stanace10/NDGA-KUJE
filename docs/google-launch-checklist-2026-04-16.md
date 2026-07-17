# Google Launch Checklist

Generated: `2026-04-16`

## Already Live

- `https://ndgakuje.org/robots.txt`
- `https://ndgakuje.org/sitemap.xml`
- schema.org structured data on public pages
- support for `google-site-verification`
- support for Google Analytics / Google Ads tag IDs
- support for Google AdSense client ID

## Still Needed

These need access to the actual Google accounts, so they cannot be completed from code alone.

1. Google Search Console
2. Add property for `https://ndgakuje.org/`
3. Verify ownership
4. Submit `https://ndgakuje.org/sitemap.xml`

1. Google Analytics / Google Ads
2. Create or confirm the GA4 property
3. Link GA4 to Google Ads
4. Add the live IDs to `.env.cloud`:

```env
GOOGLE_SITE_VERIFICATION=
GOOGLE_ANALYTICS_ID=
GOOGLE_ADS_ID=
GOOGLE_ADSENSE_CLIENT_ID=
```

1. Google Ads campaigns
2. Create search campaigns around keywords such as:
3. `girls boarding school in Abuja`
4. `Catholic secondary school Abuja`
5. `best girls school in Kuje`
6. `Notre Dame Girls' Academy Kuje Abuja`
7. `NDGA Kuje`
8. Set website conversion tracking for admissions enquiry and registration completion

## Official References

- https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- https://support.google.com/webmasters/answer/9008080
- https://support.google.com/google-ads/answer/9119707
