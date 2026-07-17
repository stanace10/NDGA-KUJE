from django.test import TestCase
from django.test import override_settings
from django.urls import reverse


class SeoSurfaceTests(TestCase):
    def test_landing_page_exposes_public_seo_metadata(self):
        response = self.client.get(reverse("dashboard:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="description"')
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'name="twitter:card"')
        self.assertContains(response, 'application/ld+json')
        self.assertContains(response, 'rel="sitemap"')
        self.assertContains(response, 'content="index, follow"')

    def test_robots_txt_exposes_sitemap_and_private_disallows(self):
        response = self.client.get(reverse("robots-txt"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(response, "Sitemap:")
        self.assertContains(response, "Disallow: /portal/")
        self.assertContains(response, "Disallow: /auth/")

    def test_sitemap_xml_lists_public_landing_url(self):
        response = self.client.get(reverse("sitemap-xml"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        self.assertContains(response, "<urlset")
        self.assertRegex(
            response.content.decode(),
            r"<loc>https?://[^<]+/</loc>",
        )

    @override_settings(PUBLIC_WEBSITE_ENABLED=True)
    def test_public_sitemap_lists_inner_public_pages_when_enabled(self):
        response = self.client.get(reverse("sitemap-xml"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "http://ndgakuje.org/about/")
        self.assertContains(response, "http://ndgakuje.org/admissions/registration/")
