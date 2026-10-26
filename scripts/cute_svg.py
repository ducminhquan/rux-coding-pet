"""Code-native SVG previews matching the cute faces drawn by the Android canvas."""
def render(face):
    ident=face['id'];color=face['color']
    items=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 360"><rect width="480" height="360" rx="28" fill="#05090d"/><g>']
    items.append('<animateTransform attributeName="transform" type="translate" values="0,-2;0,2;0,-2" dur="2.8s" repeatCount="indefinite"/>')
    items += ['<ellipse cx="98" cy="265" rx="30" ry="12" fill="#5f3047"/>','<ellipse cx="382" cy="265" rx="30" ry="12" fill="#5f3047"/>']
    for side in [90,366]:
        for i in range(3):items.append(f'<path d="M{side+i*12} 261l-4 9" stroke="#fa9bb8" stroke-width="4" stroke-linecap="round"/>')
    for index,x in enumerate([160,320]):
        if ident=='cute_love':
            items.append(f'<path d="M0 38C-68-6-36-58 0-23C36-58 68-6 0 38" fill="{color}" transform="translate({x},141.53) scale(1.62,2.106)"/>')
        elif ident=='cute_sleepy' or (ident=='cute_wink' and index==0):
            items.append(f'<path d="M{x-62} 152 Q{x} 100 {x+62} 152" fill="none" stroke="{color}" stroke-width="14.6" stroke-linecap="round"/>')
        else:
            ry=74 if ident=='cute_sad' else 61 if ident=='cute_shy' else 77 if ident=='cute_curious' and index else 99
            items.append(f'<g><ellipse cx="{x}" cy="137" rx="65" ry="{ry}" fill="{color}"/><circle cx="{x-19}" cy="{137-int(ry*.32)}" r="17.8" fill="#f7ffff"/><circle cx="{x+23}" cy="{137+int(ry*.27)}" r="7.3" fill="#f7ffff"/><animate attributeName="opacity" values="1;1;0;1;1" keyTimes="0;.8;.82;.84;1" dur="3.9s" repeatCount="indefinite"/></g>')
    if ident=='cute_sad':items.append(f'<path d="M222 290Q240 274 258 290M95 54l130-17M255 37l130 17" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
    elif ident=='cute_curious':items.append(f'<ellipse cx="240" cy="285" rx="10" ry="8" fill="none" stroke="{color}" stroke-width="5"/>')
    else:items.append(f'<path d="M221 280Q230 297 240 284Q250 297 259 280" fill="none" stroke="{color}" stroke-width="5" stroke-linecap="round"/>')
    if ident=='cute_sleepy':items.append(f'<text x="381" y="110" font-size="26" font-family="sans-serif" fill="{color}">z</text><text x="411" y="83" font-size="17" font-family="sans-serif" fill="{color}">z</text>')
    elif ident!='cute_sad':
        for x,y,r in [(87,102,10),(394,112,7)]:items.append(f'<path d="M{x} {y-r}l3 {r-3} {r-3} 3 -{r-3} 3 -3 {r-3} -3 -{r-3} -{r-3} -3 {r-3} -3Z" fill="{color}"/>')
    items.append('</g></svg>')
    return ''.join(items)
