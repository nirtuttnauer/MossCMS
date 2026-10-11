import test from 'node:test';import assert from 'node:assert/strict';import {renderHtml,metadata} from './metadata.mjs';
test('initial metadata escapes content and uses configured canonical, never request host',()=>{
 const website={siteUrl:'https://example.com',profile:{name:'Moss Example'},pages:[]};const page={slug:'blog/post',title:'</title><script>alert(1)</script>',description:'" onload="bad'};
 const html=renderHtml('<head><title>Old</title><meta name="description" content="old"></head>',website,page,{SITE_SOCIAL_IMAGE:'https://example.com/social.png?signature=expired'});
 assert.match(html,/https:\/\/example\.com\/blog\/post/);assert.ok(!html.includes('<script>'));assert.ok(!html.includes('og:image'));assert.ok(html.includes('&lt;script&gt;'));assert.equal((html.match(/<title>/g)||[]).length,1);
 assert.match(renderHtml('<head></head>',{...website,preview:{}},page),/noindex,nofollow/);
 assert.equal(metadata(website,page,{SITE_SOCIAL_IMAGE:'/social.png'}).image,'https://example.com/social.png');
});

test('social images reject credentials and transient or unsafe URLs while static HTTPS images remain usable', () => {
  const website = { siteUrl: 'https://site.example', profile: { name: 'Owner', headline: 'Headline' } };
  const page = { slug: 'home', kind: 'home' };
  for (const image of [undefined, '', 'http://site.example/image.png', 'javascript:alert(1)', 'https://user:pass@site.example/image.png', 'https://site.example/image.png?token=secret', 'https://site.example/image.png#fragment', 'https://[invalid']) {
    assert.equal(metadata(website, page, { SITE_SOCIAL_IMAGE: image }).image, undefined);
  }
  const value = metadata(website, page, { SITE_SOCIAL_IMAGE: '/social.png' });
  assert.equal(value.canonical, 'https://site.example/');
  assert.equal(value.title, 'Owner — site.example');
  assert.equal(value.description, 'Headline');
  const html = renderHtml('<head><title>Old</title><meta property="og:title" content="Old"><link rel="canonical" href="https://old.example"></head>', website, page, { SITE_SOCIAL_IMAGE: '/social.png' });
  assert.ok(!html.includes('Old'));
  assert.ok(!html.includes('old.example'));
  assert.match(html, /twitter:card" content="summary_large_image/);
  assert.match(html, /og:image" content="https:\/\/site.example\/social.png/);
});
