import { chromium } from 'playwright';
const url = 'file:///C:/Users/Hello/propertydata/site/index.html';
const b = await chromium.launch();
for (const [w,h,name] of [[1440,900,'desktop'],[390,844,'mobile']]) {
  const p = await b.newPage({ viewport:{width:w,height:h}, deviceScaleFactor:2 });
  await p.goto(url, { waitUntil:'networkidle' });
  await p.waitForTimeout(2200);
  await p.screenshot({ path:`site/_shot_${name}_top.png` });
  await p.screenshot({ path:`site/_shot_${name}_full.png`, fullPage:true });
  await p.close();
}
await b.close();
console.log('done');
