import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

import * as sass from 'sass';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const dest = path.resolve(__dirname, process.argv[2] || 'common/styles');
const skinPath = path.resolve(__dirname, '../skins');

const buildSkin = color => {
    const source = path.resolve(skinPath, color, 'front_end/styles/_custom_palette.scss');
    const skin = sass.renderSync({ file: source });
    fs.writeFileSync(path.resolve(dest, `${color}.css`), skin.css.toString(), { flag: 'w' });
    if (color === 'blue') {
        fs.writeFileSync(path.resolve(dest, 'skin.css'), skin.css.toString(), { flag: 'w' });
    }
};
