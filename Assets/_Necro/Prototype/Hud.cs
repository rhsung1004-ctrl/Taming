using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 화면 UI 전부 (빠른 검증용 IMGUI). 기준 높이 720에 맞춰 어떤 해상도에서도 같은 비율로 보인다.
    // 본편에서는 Unity UI로 다시 만든다.
    public class Hud : MonoBehaviour
    {
        class ToastMsg { public string text; public float t, life; }
        class PopMsg { public Vector3 pos; public string text; public Color color; public float t; public bool big; }
        class SayMsg { public string who, text; public Color color; public float life; }

        const float VH = 720f;
        static readonly List<ToastMsg> toasts = new List<ToastMsg>();
        static readonly List<PopMsg> pops = new List<PopMsg>();
        static readonly List<SayMsg> says = new List<SayMsg>();     // 대사 자막 (맨 앞 것이 화면에 보인다)
        static float sayT, flashT, flashLife;
        static Color flashColor;

        static readonly Color Gold = new Color(1f, 0.82f, 0.35f);
        static readonly Color Soul = new Color(0.72f, 0.45f, 1f);
        static readonly Color Panel = new Color(0.05f, 0.04f, 0.09f, 0.7f);

        float scale = 1f, vw = 1280f;
        Texture2D ringTex, dotTex, whiteTex;
        GUIStyle style, buttonStyle, fieldStyle;

        // 군단 명부에서 이름을 바꾸는 중인 소환수
        Record editing;
        string editText = "";

        public static void ClearStatic()
        {
            toasts.Clear();
            pops.Clear();
            says.Clear();
            sayT = flashT = 0f;
        }

        // 대사 자막. who: "me" = 주인공, "narr" = 해설, 그 밖에는 유닛 id
        public static void Say(string who, string text)
        {
            var m = new SayMsg { text = text, life = 2f + text.Length * 0.075f };
            if (who == "me") { m.who = "사령술사"; m.color = Soul; }
            else if (who == "narr") { m.who = null; m.color = new Color(0.82f, 0.8f, 0.88f); }
            else
            {
                UnitDef d;
                m.who = Db.Units.TryGetValue(who, out d) ? d.name : who;
                m.color = new Color(1f, 0.55f, 0.45f);
            }
            says.Add(m);
            if (says.Count > 8) says.RemoveAt(1);       // 너무 밀리면 오래 기다린 것부터 버린다
        }

        // 큰 기술을 쓸 때 화면 전체에 잠깐 번지는 색
        public static void Flash(Color c, float life)
        {
            flashColor = c;
            flashT = flashLife = life;
        }

        public static void Toast(string s, float life = 3.5f)
        {
            foreach (var t in toasts) if (t.text == s) { t.t = 0f; return; }
            toasts.Add(new ToastMsg { text = s, life = life });
            if (toasts.Count > 4) toasts.RemoveAt(0);
        }

        public static void Popup(Vector3 pos, string text, Color color, bool big = false)
        {
            pops.Add(new PopMsg { pos = pos, text = text, color = color, big = big });
            if (pops.Count > 50) pops.RemoveAt(0);
        }

        void Awake()
        {
            ringTex = Util.Circle(64, true);
            dotTex = Util.Circle(32, false);
            whiteTex = Texture2D.whiteTexture;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            for (int i = toasts.Count - 1; i >= 0; i--) { toasts[i].t += dt; if (toasts[i].t > toasts[i].life) toasts.RemoveAt(i); }
            for (int i = pops.Count - 1; i >= 0; i--) { pops[i].t += dt; if (pops[i].t > 1.1f) pops.RemoveAt(i); }
            if (says.Count > 0)
            {
                sayT += dt;
                if (sayT > says[0].life) { says.RemoveAt(0); sayT = 0f; }
            }
            if (flashT > 0f) flashT -= Time.unscaledDeltaTime;
        }

        // ───────────── 그리기 도우미 ─────────────
        void Fill(Rect r, Color c)
        {
            GUI.color = c;
            GUI.DrawTexture(r, whiteTex);
            GUI.color = Color.white;
        }

        void Text(Rect r, string s, int size, Color c, TextAnchor a)
        {
            style.fontSize = size;
            style.alignment = a;
            style.normal.textColor = new Color(0f, 0f, 0f, 0.8f * c.a);
            GUI.Label(new Rect(r.x + 1.5f, r.y + 1.5f, r.width, r.height), s, style);
            style.normal.textColor = c;
            GUI.Label(r, s, style);
        }

        void Bar(Rect r, float v, Color fg)
        {
            Fill(r, new Color(0f, 0f, 0f, 0.6f));
            Fill(new Rect(r.x + 2f, r.y + 2f, (r.width - 4f) * Mathf.Clamp01(v), r.height - 4f), fg);
        }

        bool ToGui(Camera cam, Vector3 world, out Vector2 g)
        {
            Vector3 sp = cam.WorldToScreenPoint(world);
            g = new Vector2(sp.x, Screen.height - sp.y) / scale;
            return sp.z > 0f;
        }

        void OnGUI()
        {
            var game = Game.I;
            if (game == null || game.player == null) return;
            if (style == null)
            {
                style = new GUIStyle(GUI.skin.label);
                style.fontStyle = FontStyle.Bold;
                style.wordWrap = true;
                style.clipping = TextClipping.Overflow;
                buttonStyle = new GUIStyle(GUI.skin.button);
                buttonStyle.fontSize = 13;
                fieldStyle = new GUIStyle(GUI.skin.textField);
                fieldStyle.fontSize = 15;
                fieldStyle.alignment = TextAnchor.MiddleLeft;
            }
            scale = Screen.height / VH;
            vw = Screen.width / scale;
            GUI.matrix = Matrix4x4.TRS(Vector3.zero, Quaternion.identity, new Vector3(scale, scale, 1f));

            // 군단 명부는 버튼과 입력란이 있어서 모든 이벤트를 받아야 한다
            if (game.rosterOpen) { DrawRoster(game); return; }
            editing = null;
            if (Event.current.type != EventType.Repaint) return;

            if (game.started)
            {
                DrawWorld(game);
                DrawStatus(game);
                DrawFocus(game);
                DrawQuest(game);
                DrawSkillBar(game);
                DrawCenter(game);
                DrawToasts();
                DrawSay();
                if (flashT > 0f) Fill(new Rect(0f, 0f, vw, VH), Util.WithA(flashColor, 0.28f * Mathf.Clamp01(flashT / Mathf.Max(0.01f, flashLife))));
            }
            if (game.paused) DrawPause(game);
        }

        // ───────────── 월드 위 표시 ─────────────
        void DrawWorld(Game game)
        {
            var cam = game.cam;
            var pl = game.player;
            Vector2 g;
            Vector3 cp = cam.transform.position;

            foreach (var u in Unit.Units)
            {
                if (u.IsDead) continue;
                float d2 = (u.transform.position - cp).sqrMagnitude;
                bool focus = u == pl.focus;
                bool notable = u.def.grade != UnitGrade.Common;
                bool hurt = u.hp < u.maxHp - 0.5f;
                bool named = u.Ally && u.rec != null && u.rec.name != null && d2 < 16f * 16f;
                if (!focus && !hurt && !named && !(notable && !u.Ally)) continue;
                if (d2 > (focus || notable ? 90f * 90f : 40f * 40f)) continue;
                if (!ToGui(cam, u.AimPoint + Vector3.up * (0.9f * u.def.size + 0.2f), out g)) continue;
                if (named)
                {
                    // 이름 붙은 소환수는 가까이 있으면 이름이 보인다 (고참은 ★)
                    Text(new Rect(g.x - 110f, g.y - 20f, 220f, 18f), (u.rec.veteran ? "★ " : "") + u.rec.name, 12,
                         u.rec.veteran ? Gold : new Color(0.8f, 0.7f, 1f), TextAnchor.MiddleCenter);
                    if (!hurt) continue;
                }
                float w = u.Ally ? 36f : (notable ? 90f : 54f);
                Bar(new Rect(g.x - w * 0.5f, g.y, w, u.Ally ? 6f : 9f), u.hp / u.maxHp,
                    u.Ally ? new Color(0.65f, 0.45f, 1f) : new Color(0.95f, 0.3f, 0.3f));
                if (!u.Ally && (notable || focus))
                    Text(new Rect(g.x - 110f, g.y - 22f, 220f, 20f), u.DisplayName, 14, focus ? Gold : Db.GradeColor(u.def.grade), TextAnchor.MiddleCenter);
                if (focus)
                {
                    GUI.color = Gold;
                    GUI.DrawTexture(new Rect(g.x - 9f, g.y - 44f, 18f, 18f), ringTex);
                    GUI.color = Color.white;
                }
            }

            foreach (var p in pops)
            {
                if (!ToGui(cam, p.pos + Vector3.up * p.t * 1.6f, out g)) continue;
                float a = 1f - Mathf.Clamp01((p.t - 0.6f) / 0.5f);
                Text(new Rect(g.x - 130f, g.y - 14f, 260f, 28f), p.text, p.big ? 22 : 16, Util.WithA(p.color, a), TextAnchor.MiddleCenter);
            }

            // 추모 묘비: 가까이 가면 이름과 전적이 보인다
            foreach (var f in Bond.Memorial)
            {
                if ((f.pos - pl.transform.position).sqrMagnitude > 11f * 11f) continue;
                if (!ToGui(cam, f.pos + Vector3.up * 1.9f, out g)) continue;
                Text(new Rect(g.x - 160f, g.y - 22f, 320f, 20f), f.rec.Title, 15, Soul, TextAnchor.MiddleCenter);
                Text(new Rect(g.x - 200f, g.y - 3f, 400f, 18f), f.rec.Summary, 12, new Color(0.85f, 0.82f, 0.95f), TextAnchor.MiddleCenter);
            }

            if (game.HasQuestPos)
            {
                Vector3 qp = game.QuestPos + Vector3.up * 3f;
                float dist = Vector3.Distance(qp, pl.transform.position);
                if (dist > 14f)
                {
                    bool front = ToGui(cam, qp, out g);
                    if (!front) g = new Vector2(vw - g.x, VH - 150f);
                    g.x = Mathf.Clamp(g.x, 40f, vw - 40f);
                    g.y = Mathf.Clamp(g.y, 130f, VH - 150f);
                    Text(new Rect(g.x - 20f, g.y - 18f, 40f, 36f), "◆", 26, Gold, TextAnchor.MiddleCenter);
                    Text(new Rect(g.x - 50f, g.y + 14f, 100f, 22f), Mathf.RoundToInt(dist) + "m", 14, Gold, TextAnchor.MiddleCenter);
                }
            }
        }

        // ───────────── 왼쪽 위: 주인공과 군단 ─────────────
        void DrawStatus(Game game)
        {
            var pl = game.player;
            var army = game.army;
            Fill(new Rect(12f, 10f, 372f, 148f), Panel);
            Text(new Rect(24f, 14f, 340f, 24f), "사령술사  Lv." + pl.level, 17, Color.white, TextAnchor.MiddleLeft);
            Text(new Rect(24f, 14f, 348f, 24f), Spells.TierName[pl.tier] + " 마법 · [Tab] 군단 명부", 13, pl.tier == 2 ? Gold : new Color(0.8f, 0.75f, 0.95f), TextAnchor.MiddleRight);
            Bar(new Rect(24f, 42f, 348f, 18f), pl.hp / pl.maxHp, new Color(0.85f, 0.25f, 0.3f));
            Text(new Rect(24f, 42f, 348f, 18f), Mathf.CeilToInt(pl.hp) + " / " + Mathf.RoundToInt(pl.maxHp), 12, Color.white, TextAnchor.MiddleCenter);
            Bar(new Rect(24f, 64f, 348f, 14f), pl.mana / pl.maxMana, new Color(0.45f, 0.4f, 1f));
            Text(new Rect(24f, 63f, 348f, 16f), "마나 " + Mathf.FloorToInt(pl.mana), 11, Color.white, TextAnchor.MiddleCenter);
            Bar(new Rect(24f, 82f, 348f, 6f), pl.xp / pl.XpNeed, Gold);

            int used = army.UsedSlots, max = army.MaxSlots;
            Text(new Rect(24f, 92f, 348f, 22f), "영혼 슬롯 " + used + " / " + max + "     명령: " + (army.hasPoint ? "지점 사수" : Army.ModeName[army.mode]) + " [F]", 15,
                 used >= max ? Gold : Soul, TextAnchor.MiddleLeft);
            Text(new Rect(24f, 114f, 348f, 40f), army.Summary(), 13, new Color(0.85f, 0.82f, 0.95f), TextAnchor.UpperLeft);
        }

        // ───────────── 가운데 위: 겨눈 적 ─────────────
        void DrawFocus(Game game)
        {
            var f = game.player.focus as Unit;
            if (f == null || !f.Alive) return;
            bool big = f.def.grade == UnitGrade.Hero || f.def.grade == UnitGrade.Boss;
            float w = big ? 520f : 360f;
            Rect r = new Rect(vw * 0.5f - w * 0.5f, 12f, w, 50f);
            Fill(r, Panel);
            Text(new Rect(r.x + 12f, r.y + 2f, w - 24f, 22f), "[" + Db.GradeName(f.def.grade) + "] " + f.DisplayName, 16,
                 Db.GradeColor(f.def.grade), TextAnchor.MiddleLeft);
            Bar(new Rect(r.x + 12f, r.y + 27f, w - 24f, 15f), f.hp / f.maxHp, new Color(0.95f, 0.3f, 0.3f));
            Text(new Rect(r.x + 12f, r.y + 26f, w - 24f, 17f), Mathf.CeilToInt(f.hp) + " / " + Mathf.RoundToInt(f.maxHp), 11, Color.white, TextAnchor.MiddleCenter);
        }

        void DrawQuest(Game game)
        {
            Rect r = new Rect(vw - 372f, 10f, 360f, 70f);
            Fill(r, Panel);
            Text(new Rect(r.x + 12f, r.y + 4f, 336f, 62f), game.QuestText, 14, new Color(1f, 0.93f, 0.72f), TextAnchor.MiddleLeft);
        }

        // ───────────── 아래: 기술 막대 ─────────────
        void Slot(float x, float y, string key, string name, float cd01, bool ok, Color tint)
        {
            const float W = 92f, H = 62f;
            Rect r = new Rect(x, y, W, H);
            Fill(r, ok ? Panel : new Color(0.12f, 0.05f, 0.05f, 0.7f));
            Fill(new Rect(x, y, W, 3f), Util.WithA(tint, ok ? 0.9f : 0.3f));
            if (cd01 > 0f) Fill(new Rect(x, y + H * (1f - cd01), W, H * cd01), new Color(0f, 0f, 0f, 0.6f));
            Text(new Rect(x, y + 6f, W, 24f), key, 16, ok ? Gold : new Color(0.6f, 0.55f, 0.5f), TextAnchor.MiddleCenter);
            Text(new Rect(x, y + 32f, W, 22f), name, 13, ok ? Color.white : new Color(0.6f, 0.6f, 0.6f), TextAnchor.MiddleCenter);
        }

        void DrawSkillBar(Game game)
        {
            var pl = game.player;
            var army = game.army;
            bool ride = pl.Riding;
            const float W = 92f, gap = 6f;
            bool hasDragon = army.dragon != null;
            int t = pl.tier;
            int n = 8 + (pl.hasCrown ? 1 : 0) + (hasDragon ? 1 : 0);
            float x = vw * 0.5f - (n * W + (n - 1) * gap) * 0.5f, y = VH - 76f;
            float step = W + gap;
            Slot(x, y, "좌클릭", ride ? "브레스" : Spells.BasicName[t], 0f, true, Soul);
            Slot(x + step, y, "우클릭", Spells.SpearName[t], Mathf.Clamp01(pl.spearCd / Spells.SpearCd[t]), !ride && pl.mana >= Spells.SpearMana[t], new Color(0.95f, 0.92f, 0.8f));
            Slot(x + step * 2, y, "Q", Spells.BlastName[t], Mathf.Clamp01(pl.blastCd / Spells.BlastCd[t]), pl.mana >= Spells.BlastMana[t], new Color(0.6f, 1f, 0.35f));
            Slot(x + step * 3, y, "R", Spells.BuffName[t], Mathf.Clamp01(pl.buffCd / Spells.BuffCd[t]), pl.mana >= Spells.BuffMana[t] && army.Count > 0, new Color(1f, 0.35f, 0.4f));
            Slot(x + step * 4, y, "E", Spells.RaiseName[t], 0f, true, Soul);
            Slot(x + step * 5, y, "F · 휠클릭", army.hasPoint ? "지점 사수" : "명령: " + Army.ModeName[army.mode], 0f, true, new Color(0.6f, 0.8f, 1f));
            Slot(x + step * 6, y, ride ? "Space/Ctrl" : "Shift", ride ? "상승/하강" : "대시", ride ? 0f : Mathf.Clamp01(pl.dashCd / PlayerCtl.DashCdMax), true, Color.white);
            Slot(x + step * 7, y, "V", ride ? "내리기" : "본드래곤", 0f, hasDragon, Gold);
            int k = 8;
            if (hasDragon)
                Slot(x + step * k++, y, "Z", "강림", Mathf.Clamp01(pl.descentCd / Spells.DescentCd), !ride && pl.mana >= Spells.DescentMana, Gold);
            if (pl.hasCrown)
            {
                Slot(x + step * k, y, "G", Spells.CrownName[pl.crownIdx], Mathf.Clamp01(pl.legionCd / Spells.LegionCd), !ride && pl.mana >= Spells.LegionMana, Gold);
                Text(new Rect(x + step * k - 20f, y - 20f, W + 40f, 18f), "[T] " + Spells.CrownSchool[pl.crownIdx], 12, Gold, TextAnchor.MiddleCenter);
            }
        }

        // ───────────── 화면 가운데: 조준점, 지배 진행, 안내 ─────────────
        void DrawCenter(Game game)
        {
            var pl = game.player;
            var army = game.army;
            float cx = vw * 0.5f, cy = VH * 0.5f;
            if (!game.paused)
            {
                GUI.color = new Color(1f, 1f, 1f, 0.75f);
                GUI.DrawTexture(new Rect(cx - 3f, cy - 3f, 6f, 6f), dotTex);
                GUI.color = Color.white;
            }

            if (army.holdTarget != null)
            {
                var d = army.holdTarget.def;
                Rect r = new Rect(cx - 170f, cy + 90f, 340f, 22f);
                Text(new Rect(r.x, r.y - 28f, r.width, 24f), Util.EulReul(d.NameFor(true)) + " 향해 손을 내미는 중…  E를 누르고 있으세요", 16, Soul, TextAnchor.MiddleCenter);
                Bar(r, army.holdT / Mathf.Max(0.01f, army.holdNeed), Soul);
                return;
            }

            // 근처 시체 안내
            int commons = 0;
            Corpse big = null;
            float bigD = float.MaxValue;
            foreach (var c in Corpse.All)
            {
                float dist = Vector3.Distance(c.transform.position, pl.transform.position);
                if (dist > army.RaiseRange) continue;
                if (c.def.grade == UnitGrade.Common || (pl.tier >= 2 && c.def.grade == UnitGrade.Elite)) commons++;
                else if (dist < bigD && dist <= 14f) { bigD = dist; big = c; }
            }
            string hint = null;
            if (big != null)
                hint = "E 길게 — " + Util.EulReul(big.def.NameFor(true)) + " 지배 (슬롯 " + Db.SlotCost(big.def.grade) + "칸 · 마나 " + Mathf.RoundToInt(army.RaiseMana(big.def.grade)) + ")";
            else if (commons > 0)
                hint = "E — " + Spells.RaiseName[pl.tier] + ": 시체 " + commons + "구 (일반 한 구당 슬롯 1칸 · 마나 " + Mathf.RoundToInt(army.RaiseMana(UnitGrade.Common)) + ")";
            if (hint != null) Text(new Rect(cx - 300f, cy + 96f, 600f, 26f), hint, 17, Soul, TextAnchor.MiddleCenter);

            if (pl.Riding)
                Text(new Rect(cx - 300f, VH - 104f, 600f, 22f), "고도 " + Mathf.RoundToInt(pl.transform.position.y) + "m", 15,
                     new Color(0.8f, 0.85f, 1f), TextAnchor.MiddleCenter);
        }

        void DrawToasts()
        {
            float y = 96f;
            foreach (var t in toasts)
            {
                float a = Mathf.Clamp01((t.life - t.t) / 0.4f);
                Rect r = new Rect(vw * 0.5f - 330f, y, 660f, 32f);
                Fill(r, new Color(0f, 0f, 0f, 0.55f * a));
                Text(r, t.text, 16, new Color(1f, 1f, 1f, a), TextAnchor.MiddleCenter);
                y += 36f;
            }
        }

        // ───────────── 대사 자막 ─────────────
        void DrawSay()
        {
            if (says.Count == 0) return;
            var m = says[0];
            float a = Mathf.Clamp01(sayT / 0.2f) * Mathf.Clamp01((m.life - sayT) / 0.3f);
            Rect r = new Rect(vw * 0.5f - 400f, VH - 184f, 800f, 70f);
            Fill(r, new Color(0.03f, 0.02f, 0.07f, 0.72f * a));
            Fill(new Rect(r.x, r.y, 4f, r.height), Util.WithA(m.color, a));
            if (m.who != null)
            {
                Text(new Rect(r.x + 18f, r.y + 6f, 760f, 22f), m.who, 15, Util.WithA(m.color, a), TextAnchor.MiddleLeft);
                Text(new Rect(r.x + 18f, r.y + 27f, 764f, 40f), m.text, 17, new Color(1f, 1f, 1f, a), TextAnchor.UpperLeft);
            }
            else Text(new Rect(r.x + 18f, r.y + 6f, 764f, 58f), m.text, 16, Util.WithA(m.color, a), TextAnchor.MiddleLeft);
        }

        // ───────────── 군단 명부 (Tab): 이름과 전적, 추모 ─────────────
        void DrawRoster(Game game)
        {
            var army = game.army;
            float cx = vw * 0.5f;
            Fill(new Rect(0f, 0f, vw, VH), new Color(0.03f, 0.02f, 0.07f, 0.88f));
            Text(new Rect(0f, 24f, vw, 40f), "군단 명부", 30, Soul, TextAnchor.MiddleCenter);
            Text(new Rect(0f, 62f, vw, 22f), "Tab 또는 Esc로 닫기 · 이름 붙은 소환수를 잃으면 봉인의 제단 곁에 묘비가 세워집니다", 14,
                 new Color(0.85f, 0.82f, 0.95f), TextAnchor.MiddleCenter);

            const float W = 900f, RowH = 40f;
            float x = cx - W * 0.5f, y = 100f;
            int shown = 0, unnamed = 0;
            foreach (var u in army.units)
            {
                if (u == null || u.rec == null) continue;
                var r = u.rec;
                if (r.name == null && r.grade == UnitGrade.Common) { unnamed++; continue; }
                if (shown >= 9) continue;
                Rect row = new Rect(x, y, W, RowH - 4f);
                Fill(row, Panel);
                Fill(new Rect(x, y, 4f, RowH - 4f), Db.GradeColor(r.grade));
                if (editing == r)
                {
                    GUI.SetNextControlName("necroName");
                    editText = GUI.TextField(new Rect(x + 14f, y + 5f, 150f, 26f), editText, 8, fieldStyle);
                    GUI.FocusControl("necroName");
                }
                else
                    Text(new Rect(x + 14f, y, 250f, RowH - 4f), (r.veteran ? "★ " : "") + (r.name ?? "(이름 없음)"), 17,
                         r.veteran ? Gold : Color.white, TextAnchor.MiddleLeft);
                Text(new Rect(x + 176f, y, 200f, RowH - 4f), "[" + Db.GradeName(r.grade) + "] " + r.unitName + "  Lv." + u.level, 14,
                     Db.GradeColor(r.grade), TextAnchor.MiddleLeft);
                Text(new Rect(x + 384f, y, 320f, RowH - 4f), r.Summary, 13, new Color(0.85f, 0.82f, 0.95f), TextAnchor.MiddleLeft);
                if (editing == r)
                {
                    if (GUI.Button(new Rect(x + W - 190f, y + 5f, 86f, 26f), "확인", buttonStyle))
                    {
                        string nm = editText.Trim();
                        if (nm.Length > 0) r.name = nm;
                        editing = null;
                    }
                    if (GUI.Button(new Rect(x + W - 98f, y + 5f, 86f, 26f), "취소", buttonStyle)) editing = null;
                }
                else
                {
                    if (GUI.Button(new Rect(x + W - 190f, y + 5f, 86f, 26f), "이름 쓰기", buttonStyle))
                    {
                        editing = r;
                        editText = r.name ?? "";
                    }
                    if (GUI.Button(new Rect(x + W - 98f, y + 5f, 86f, 26f), "다른 이름", buttonStyle)) r.name = Bond.NewName();
                }
                y += RowH;
                shown++;
            }
            if (shown == 0)
            {
                Text(new Rect(x, y, W, 60f), "아직 이름 붙은 소환수가 없어요.\n정예 이상을 지배하면 이름을 받고, 일반 소환수는 오래 살아남아 '고참'이 되면 이름을 얻어요.", 15,
                     new Color(0.85f, 0.82f, 0.95f), TextAnchor.MiddleCenter);
                y += 64f;
            }
            Text(new Rect(x, y + 2f, W, 22f), "이름 없는 소환수 " + unnamed + "마리 — 전투 " + Bond.VeteranBattles + "번 또는 처치 " + Bond.VeteranKills +
                 "번을 넘기면 ★고참이 되어 이름을 얻고 조금 강해집니다", 13, new Color(0.7f, 0.68f, 0.8f), TextAnchor.MiddleLeft);
            y += 40f;

            Text(new Rect(x, y, W, 26f), "추모 — 쓰러진 이름들", 18, Soul, TextAnchor.MiddleLeft);
            y += 30f;
            if (Bond.Memorial.Count == 0)
                Text(new Rect(x, y, W, 22f), "아직 아무도 잃지 않았어요.", 14, new Color(0.7f, 0.68f, 0.8f), TextAnchor.MiddleLeft);
            for (int i = Bond.Memorial.Count - 1, c = 0; i >= 0 && c < 7 && y < VH - 30f; i--, c++)
            {
                var r = Bond.Memorial[i].rec;
                Text(new Rect(x + 8f, y, 330f, 22f), r.Title, 15, Color.white, TextAnchor.MiddleLeft);
                Text(new Rect(x + 340f, y, 550f, 22f), r.Summary, 13, new Color(0.85f, 0.82f, 0.95f), TextAnchor.MiddleLeft);
                y += 24f;
            }
        }

        // ───────────── 시작·일시정지 화면 ─────────────
        static readonly string[,] Keys =
        {
            { "WASD · 마우스", "이동 · 시점" },
            { "마우스 왼쪽", "영혼 화살 → 영혼 탄막 → 영혼 폭풍 (탑승 중에는 브레스)" },
            { "마우스 오른쪽", "뼈 창 → 뼈 창 비 → 거신의 척추" },
            { "E", "시체 지배 → 대량 지배 → 왕관의 부름 (정예 이상은 길게)" },
            { "Q", "시체 폭발 → 연쇄 폭발 → 망자의 해일" },
            { "R", "군단 강화 → 광란 → 불사의 군단" },
            { "F · 휠 클릭", "군단 명령 (돌격 / 호위 / 후퇴) · 겨눈 지점으로 보내기" },
            { "Shift · Space", "대시 (잠깐 무적) · 점프" },
            { "V · Z", "본드래곤 탑승 (Space 상승, Ctrl 하강) · 강림" },
            { "G · T", "왕관 스킬 쓰기 · 고르기 (왕관 조각을 되찾은 뒤, 5종)" },
            { "Tab · Esc", "군단 명부 (이름과 전적) · 일시정지" },
            { "F1 · F2", "테스트: 기술 단계 전환 · 애니풍 룩 미리보기" },
        };

        void DrawPause(Game game)
        {
            Fill(new Rect(0f, 0f, vw, VH), new Color(0.03f, 0.02f, 0.07f, game.started ? 0.72f : 0.86f));
            float cx = vw * 0.5f;
            Text(new Rect(0f, 56f, vw, 50f), "사령술사 3D — 프로토타입 v0.3", 36, Soul, TextAnchor.MiddleCenter);
            Text(new Rect(0f, 100f, vw, 28f), "묘지기를 쓰러뜨리면 상급 마법, 고룡을 쓰러뜨리면 금주, 망자의 군주를 쓰러뜨리면 왕관 스킬이 열립니다", 16,
                 new Color(0.85f, 0.82f, 0.95f), TextAnchor.MiddleCenter);
            int rows = Keys.GetLength(0);
            float y = 146f;
            Fill(new Rect(cx - 330f, y - 12f, 660f, rows * 34f + 24f), Panel);
            for (int i = 0; i < rows; i++)
            {
                Text(new Rect(cx - 310f, y + i * 34f, 160f, 30f), Keys[i, 0], 17, Gold, TextAnchor.MiddleLeft);
                Text(new Rect(cx - 150f, y + i * 34f, 470f, 30f), Keys[i, 1], 15, Color.white, TextAnchor.MiddleLeft);
            }
            float a = 0.6f + 0.4f * Mathf.Abs(Mathf.Sin(Time.unscaledTime * 2.5f));
            Text(new Rect(0f, y + rows * 34f + 34f, vw, 36f), game.started ? "화면을 클릭하면 계속합니다" : "화면을 클릭하면 시작합니다", 24,
                 Util.WithA(Color.white, a), TextAnchor.MiddleCenter);
        }
    }
}
