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

        const float VH = 720f;
        static readonly List<ToastMsg> toasts = new List<ToastMsg>();
        static readonly List<PopMsg> pops = new List<PopMsg>();

        static readonly Color Gold = new Color(1f, 0.82f, 0.35f);
        static readonly Color Soul = new Color(0.72f, 0.45f, 1f);
        static readonly Color Panel = new Color(0.05f, 0.04f, 0.09f, 0.7f);

        float scale = 1f, vw = 1280f;
        Texture2D ringTex, dotTex, whiteTex;
        GUIStyle style;

        public static void ClearStatic()
        {
            toasts.Clear();
            pops.Clear();
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
            if (Event.current.type != EventType.Repaint) return;
            var game = Game.I;
            if (game == null || game.player == null) return;
            if (style == null)
            {
                style = new GUIStyle(GUI.skin.label);
                style.fontStyle = FontStyle.Bold;
                style.wordWrap = true;
                style.clipping = TextClipping.Overflow;
            }
            scale = Screen.height / VH;
            vw = Screen.width / scale;
            GUI.matrix = Matrix4x4.TRS(Vector3.zero, Quaternion.identity, new Vector3(scale, scale, 1f));

            if (game.started)
            {
                DrawWorld(game);
                DrawStatus(game);
                DrawFocus(game);
                DrawQuest(game);
                DrawSkillBar(game);
                DrawCenter(game);
                DrawToasts();
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
                if (!focus && !hurt && !(notable && !u.Ally)) continue;
                if (d2 > (focus || notable ? 90f * 90f : 40f * 40f)) continue;
                if (!ToGui(cam, u.AimPoint + Vector3.up * (0.9f * u.def.size + 0.2f), out g)) continue;
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
            Bar(new Rect(24f, 42f, 348f, 18f), pl.hp / pl.maxHp, new Color(0.85f, 0.25f, 0.3f));
            Text(new Rect(24f, 42f, 348f, 18f), Mathf.CeilToInt(pl.hp) + " / " + Mathf.RoundToInt(pl.maxHp), 12, Color.white, TextAnchor.MiddleCenter);
            Bar(new Rect(24f, 64f, 348f, 14f), pl.mana / pl.maxMana, new Color(0.45f, 0.4f, 1f));
            Text(new Rect(24f, 63f, 348f, 16f), "마나 " + Mathf.FloorToInt(pl.mana), 11, Color.white, TextAnchor.MiddleCenter);
            Bar(new Rect(24f, 82f, 348f, 6f), pl.xp / pl.XpNeed, Gold);

            int used = army.UsedSlots, max = army.MaxSlots;
            Text(new Rect(24f, 92f, 348f, 22f), "영혼 슬롯 " + used + " / " + max + "     명령: " + Army.ModeName[army.mode] + " [F]", 15,
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
            int n = 8;
            float x = vw * 0.5f - (n * W + (n - 1) * gap) * 0.5f, y = VH - 76f;
            float step = W + gap;
            Slot(x, y, "좌클릭", ride ? "브레스" : "영혼 화살", 0f, true, Soul);
            Slot(x + step, y, "우클릭", "뼈 창", Mathf.Clamp01(pl.spearCd / PlayerCtl.SpearCdMax), !ride && pl.mana >= PlayerCtl.SpearMana, new Color(0.95f, 0.92f, 0.8f));
            Slot(x + step * 2, y, "Q", "시체 폭발", Mathf.Clamp01(pl.blastCd / PlayerCtl.BlastCdMax), pl.mana >= PlayerCtl.BlastMana, new Color(0.6f, 1f, 0.35f));
            Slot(x + step * 3, y, "R", "군단 강화", Mathf.Clamp01(pl.buffCd / PlayerCtl.BuffCdMax), pl.mana >= PlayerCtl.BuffMana && army.Count > 0, new Color(1f, 0.35f, 0.4f));
            Slot(x + step * 4, y, "E", "시체 지배", 0f, true, Soul);
            Slot(x + step * 5, y, "F", "명령: " + Army.ModeName[army.mode], 0f, true, new Color(0.6f, 0.8f, 1f));
            Slot(x + step * 6, y, ride ? "Space/Ctrl" : "Shift", ride ? "상승/하강" : "대시", ride ? 0f : Mathf.Clamp01(pl.dashCd / PlayerCtl.DashCdMax), true, Color.white);
            bool hasDragon = army.dragon != null;
            Slot(x + step * 7, y, "V", ride ? "내리기" : "본드래곤", 0f, hasDragon, Gold);
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
                Text(new Rect(r.x, r.y - 28f, r.width, 24f), d.NameFor(true) + " 지배 중…  E를 누르고 있으세요", 16, Soul, TextAnchor.MiddleCenter);
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
                if (dist > Army.RaiseRange) continue;
                if (c.def.grade == UnitGrade.Common) commons++;
                else if (dist < bigD) { bigD = dist; big = c; }
            }
            string hint = null;
            if (big != null)
                hint = "E 길게 — " + Util.EulReul(big.def.NameFor(true)) + " 지배 (슬롯 " + Db.SlotCost(big.def.grade) + "칸 · 마나 " + Mathf.RoundToInt(Db.RaiseMana(big.def.grade)) + ")";
            else if (commons > 0)
                hint = "E — 시체 " + commons + "구 지배 (구당 슬롯 1칸 · 마나 8)";
            if (hint != null) Text(new Rect(cx - 300f, cy + 96f, 600f, 26f), hint, 17, Soul, TextAnchor.MiddleCenter);

            if (pl.Riding)
                Text(new Rect(cx - 300f, VH - 108f, 600f, 22f), "고도 " + Mathf.RoundToInt(pl.transform.position.y) + "m", 15,
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

        // ───────────── 시작·일시정지 화면 ─────────────
        static readonly string[,] Keys =
        {
            { "WASD · 마우스", "이동 · 시점" },
            { "마우스 왼쪽", "영혼 화살 (탑승 중에는 브레스)" },
            { "마우스 오른쪽", "뼈 창 — 강한 한 방과 범위 피해" },
            { "E", "시체 지배 — 일반은 한 번, 정예 이상은 길게" },
            { "Q", "시체 폭발 — 근처 시체를 터뜨려 범위 피해" },
            { "R", "군단 강화 — 공격력 증가와 회복" },
            { "F", "군단 명령 — 돌격 / 호위 / 후퇴" },
            { "Shift · Space", "대시 (잠깐 무적) · 점프" },
            { "V", "본드래곤 탑승 — Space 상승, Ctrl 하강" },
            { "Esc", "일시정지" },
        };

        void DrawPause(Game game)
        {
            Fill(new Rect(0f, 0f, vw, VH), new Color(0.03f, 0.02f, 0.07f, game.started ? 0.72f : 0.86f));
            float cx = vw * 0.5f;
            Text(new Rect(0f, 70f, vw, 50f), "사령술사 3D — 프로토타입", 36, Soul, TextAnchor.MiddleCenter);
            Text(new Rect(0f, 122f, vw, 28f), "쓰러뜨린 적을 일으켜 군단을 만들고, 고룡의 시체로 본드래곤을 만드세요", 17,
                 new Color(0.85f, 0.82f, 0.95f), TextAnchor.MiddleCenter);
            int rows = Keys.GetLength(0);
            float y = 180f;
            Fill(new Rect(cx - 330f, y - 12f, 660f, rows * 34f + 24f), Panel);
            for (int i = 0; i < rows; i++)
            {
                Text(new Rect(cx - 310f, y + i * 34f, 200f, 30f), Keys[i, 0], 17, Gold, TextAnchor.MiddleLeft);
                Text(new Rect(cx - 100f, y + i * 34f, 420f, 30f), Keys[i, 1], 16, Color.white, TextAnchor.MiddleLeft);
            }
            float a = 0.6f + 0.4f * Mathf.Abs(Mathf.Sin(Time.unscaledTime * 2.5f));
            Text(new Rect(0f, y + rows * 34f + 34f, vw, 36f), game.started ? "화면을 클릭하면 계속합니다" : "화면을 클릭하면 시작합니다", 24,
                 Util.WithA(Color.white, a), TextAnchor.MiddleCenter);
        }
    }
}
