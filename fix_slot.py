import re

with open('C:/Users/smcpa/Documents/Claude code/ipo_game/templates_web/game.html', encoding='utf-8') as f:
    content = f.read()

# ── Fix 1: fortune detection + sound calls ──
OLD = (
    "      // 突発イベントの正負でリール枠色を変える\n"
    "      const badFortunes  = ['⚔️','🦠','💣','🌊','📉','⚡'];\n"
    "      const goodFortunes = ['📈'];\n"
    "      if (badFortunes.some(s => r3val.includes(s.replace(/\\uFE0F/g,'')))) {\n"
    "        r3el.classList.add('fortune-bad');\n"
    "      } else if (goodFortunes.includes(r3val)) {\n"
    "        r3el.classList.add('fortune-good');\n"
    "      } else {\n"
    "        r3el.classList.add('fortune-mid');\n"
    "      }"
)
NEW = (
    "      // 突発イベントの正負でリール枠色を変える\n"
    "      const badFortunes  = ['⚔️','⚔','🦠','💣','🌊','📉','⚡'];\n"
    "      const goodFortunes = ['📈'];\n"
    "      let fortuneType = 'mid';\n"
    "      // vcls が明示的に bad/good を示す場合は優先\n"
    "      if (vcls && vcls.includes('bad'))       fortuneType = 'bad';\n"
    "      else if (vcls && vcls.includes('good'))  fortuneType = 'good';\n"
    "      else if (badFortunes.some(s => r3val.includes(s.replace(/\\uFE0F/g,'')))) fortuneType = 'bad';\n"
    "      else if (goodFortunes.includes(r3val))   fortuneType = 'good';\n"
    "\n"
    "      r3el.classList.add('fortune-' + fortuneType);\n"
    "\n"
    "      // 結果サウンド（200ms後に再生）\n"
    "      setTimeout(function() {\n"
    "        if (window._slotSfx) {\n"
    "          if      (fortuneType === 'good') window._slotSfx.fanfare();\n"
    "          else if (fortuneType === 'bad')  window._slotSfx.doom();\n"
    "          else                              window._slotSfx.calm();\n"
    "        }\n"
    "      }, 200);"
)

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print("Fix1: OK")
else:
    print("Fix1: NOT FOUND - showing actual section:")
    idx = content.find("突発イベントの正負")
    print(repr(content[idx:idx+500]))

# ── Fix 2: resumeBGM in renderButtons for continue-style buttons ──
OLD2 = (
    "        if (btn.value !== '__ADVISOR__') {\n"
    "          btnBarEl.querySelectorAll('button').forEach(function(b) {\n"
    "            b.disabled = true;\n"
    "            b.style.opacity = '0.5';\n"
    "          });\n"
    "        }\n"
    "        window.gameAction(btn.value);"
)
NEW2 = (
    "        if (btn.value !== '__ADVISOR__') {\n"
    "          btnBarEl.querySelectorAll('button').forEach(function(b) {\n"
    "            b.disabled = true;\n"
    "            b.style.opacity = '0.5';\n"
    "          });\n"
    "        }\n"
    "        // ターンボタン（continue）押下時にBGMを再開\n"
    "        if (btn.style === 'continue' && window._slotSfx) {\n"
    "          window._slotSfx.resumeBGM();\n"
    "        }\n"
    "        window.gameAction(btn.value);"
)

if OLD2 in content:
    content = content.replace(OLD2, NEW2, 1)
    print("Fix2: OK")
else:
    print("Fix2: NOT FOUND")

out_path = 'C:/Users/smcpa/Documents/Claude code/ipo_game/templates_web/game_patched.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Saved to game_patched.html")
