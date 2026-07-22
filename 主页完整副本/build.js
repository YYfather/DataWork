const fs = require('fs');
const path = require('path');
const { minify } = require('terser');
const csso = require('csso');
const htmlMinifier = require('html-minifier-terser');

const MODULES = ['vault', 'english'];

async function buildModule(moduleName) {
  console.log(`\n🔨 Building ${moduleName}...`);

  const moduleDir = path.join(__dirname, moduleName);
  const assetsDir = path.join(moduleDir, 'assets');

  // 1. 压缩 JS
  const jsPath = path.join(assetsDir, 'js', 'app.js');
  if (fs.existsSync(jsPath)) {
    const js = fs.readFileSync(jsPath, 'utf8');
    const minified = await minify(js, {
      compress: { drop_console: true },
      mangle: true,
    });
    const outputPath = path.join(assetsDir, 'js', 'app.min.js');
    fs.writeFileSync(outputPath, minified.code);
    console.log(`  ✅ JS: ${js.length} → ${minified.code.length} bytes`);
  } else {
    console.log(`  ⚠️ JS not found: ${jsPath}`);
  }

  // 2. 压缩 CSS
  const cssPath = path.join(assetsDir, 'css', 'styles.css');
  if (fs.existsSync(cssPath)) {
    const css = fs.readFileSync(cssPath, 'utf8');
    const minified = csso.minify(css);
    const outputPath = path.join(assetsDir, 'css', 'styles.min.css');
    fs.writeFileSync(outputPath, minified.css);
    console.log(`  ✅ CSS: ${css.length} → ${minified.css.length} bytes`);
  } else {
    console.log(`  ⚠️ CSS not found: ${cssPath}`);
  }

  // 3. 压缩 HTML
  const htmlPath = path.join(moduleDir, 'index.html');
  if (fs.existsSync(htmlPath)) {
    const html = fs.readFileSync(htmlPath, 'utf8');
    const minified = await htmlMinifier.minify(html, {
      collapseWhitespace: true,
      removeComments: true,
      minifyCSS: true,
      minifyJS: true,
    });
    const outputPath = path.join(moduleDir, 'index.min.html');
    fs.writeFileSync(outputPath, minified);
    console.log(`  ✅ HTML: ${html.length} → ${minified.length} bytes`);
  } else {
    console.log(`  ⚠️ HTML not found: ${htmlPath}`);
  }
}

async function main() {
  const target = process.argv[2] || 'all';

  console.log(`\n📦 Web Toolbox Build System v2.0`);

  if (target === 'all') {
    for (const mod of MODULES) {
      await buildModule(mod);
    }
  } else if (MODULES.includes(target)) {
    await buildModule(target);
  } else {
    console.error(`\n❌ Unknown module: ${target}`);
    console.log(`\nAvailable modules: ${MODULES.join(', ')}`);
    process.exit(1);
  }

  console.log('\n✨ Build complete!\n');
}

main().catch(console.error);
