using System.Collections.Generic;
using UnityEngine;

// 화면 UI 전부 (멀티터치 가상 조이스틱, 버튼, 체력바, 미니게임, 알림)
// 기준 해상도 높이 720으로 맞춰 어떤 기기에서도 같은 비율로 보인다.
[DefaultExecutionOrder(-100)]
public class GameHUD : MonoBehaviour
{
    public static GameHUD I;

    class VBtn
    {
        public bool rect, popup, visible, highlight, enabled = true, down, held;
        public Vector2 c;
        public float r;
        public Rect box;
        public int ptr = NoPtr;
        public string label;
        public Color color;
        public float fill = 1f;   // 쿨타임 (1 = 사용 가능)
        public bool Contains(Vector2 p) { return rect ? box.Contains(p) : (p - c).sqrMagnitude <= r * r * 1.15f; }
    }

    class ToastMsg { public string text; public float t, life; }
    class PopMsg { public Vector3 pos; public string text; public Color color; public float t; public bool big; }

    const int NoPtr = int.MinValue;
    const float VH = 720f;
    const float JoyR = 95f;

    public Vector2 Move, CamDelta;
    public bool FoodMenu, MountMenu, PetPanel;

    readonly Dictionary<string, VBtn> btns = new Dictionary<string, VBtn>();
    readonly List<VBtn> order = new List<VBtn>();
    static readonly List<ToastMsg> toasts = new List<ToastMsg>();
    static readonly List<PopMsg> pops = new List<PopMsg>();

    float scale = 1f, vw = 1280f;
    int joyPtr = NoPtr, camPtr = NoPtr;
    Vector2 joyCenter, joyKnob, camLast, camStart;
    float camStartTime;

    Texture2D circleTex, ringTex, whiteTex;
    GUIStyle style;

    static readonly Color BaseC = new Color(0.12f, 0.14f, 0.22f, 0.72f);
    static readonly Color Gold = new Color(1f, 0.82f, 0.3f);

    public static void ClearStatic()
    {
        toasts.Clear();
        pops.Clear();
    }

    public static void Toast(string s, float life = 3.5f)
    {
        toasts.Add(new ToastMsg { text = s, life = life });
        if (toasts.Count > 4) toasts.RemoveAt(0);
    }

    public static void Popup(Vector3 pos, string text, Color color, bool big = false)
    {
        pops.Add(new PopMsg { pos = pos, text = text, color = color, big = big });
        if (pops.Count > 40) pops.RemoveAt(0);
    }

    void Awake()
    {
        I = this;
        circleTex = Util.Circle(128, false);
        ringTex = Util.Circle(128, true);
        whiteTex = Texture2D.whiteTexture;
    }

    VBtn B(string id)
    {
        VBtn b;
        if (!btns.TryGetValue(id, out b))
        {
            b = new VBtn();
            btns[id] = b;
            order.Add(b);
        }
        return b;
    }

    public bool Down(string id) { VBtn b; return btns.TryGetValue(id, out b) && b.down; }
    public bool Held(string id) { VBtn b; return btns.TryGetValue(id, out b) && b.held; }

    VBtn Circle(string id, Vector2 c, float r, string label, Color col, bool enabled = true, bool popup = false)
    {
        var b = B(id);
        b.rect = false; b.c = c; b.r = r; b.label = label; b.color = col;
        b.visible = true; b.enabled = enabled; b.popup = popup; b.highlight = false; b.fill = 1f;
        return b;
    }

    VBtn RectBtn(string id, Rect r, string label, Color col)
    {
        var b = B(id);
        b.rect = true; b.box = r; b.label = label; b.color = col;
        b.visible = true; b.enabled = true; b.popup = true; b.highlight = false; b.fill = 1f;
        return b;
    }

    // ───────────── 입력 처리 ─────────────
    void Update()
    {
        scale = Screen.height / VH;
        vw = Screen.width / scale;
        CamDelta = Vector2.zero;
        foreach (var b in order) { b.visible = false; b.down = false; }
        Layout();
        ProcessPointers();
        foreach (var b in order)
        {
            if (!b.visible) b.ptr = NoPtr;
            b.held = b.ptr != NoPtr && b.enabled;
        }
        KeyboardMerge();

        Vector2 m = Vector2.zero;
        if (joyPtr != NoPtr)
        {
            Vector2 d = Vector2.ClampMagnitude(joyKnob - joyCenter, JoyR);
            m = new Vector2(d.x, -d.y) / JoyR;
        }
        Move = Vector2.ClampMagnitude(m + TouchInput.KeyMove, 1f);

        float dt = Time.deltaTime;
        for (int i = toasts.Count - 1; i >= 0; i--) { toasts[i].t += dt; if (toasts[i].t > toasts[i].life) toasts.RemoveAt(i); }
        for (int i = pops.Count - 1; i >= 0; i--) { pops[i].t += dt; if (pops[i].t > 1.2f) pops.RemoveAt(i); }
    }

    static bool Has(List<PointerInfo> list, int id)
    {
        foreach (var p in list) if (p.id == id) return true;
        return false;
    }

    void ProcessPointers()
    {
        var ptrs = TouchInput.Pointers;
        if (joyPtr != NoPtr && !Has(ptrs, joyPtr)) joyPtr = NoPtr;
        if (camPtr != NoPtr && !Has(ptrs, camPtr)) camPtr = NoPtr;
        foreach (var b in order) if (b.ptr != NoPtr && !Has(ptrs, b.ptr)) b.ptr = NoPtr;

        bool popupOpen = FoodMenu || MountMenu || PetPanel;
        bool taming = GameManager.I != null && GameManager.I.taming.active;

        foreach (var p in ptrs)
        {
            Vector2 g = new Vector2(p.pos.x, Screen.height - p.pos.y) / scale;
            if (p.began)
            {
                VBtn hit = null;
                for (int i = order.Count - 1; i >= 0 && hit == null; i--)
                {
                    var b = order[i];
                    if (b.visible && b.popup && b.Contains(g)) hit = b;
                }
                if (hit == null && !popupOpen)
                {
                    for (int i = order.Count - 1; i >= 0 && hit == null; i--)
                    {
                        var b = order[i];
                        if (b.visible && !b.popup && b.Contains(g)) hit = b;
                    }
                }

                if (hit != null)
                {
                    hit.ptr = p.id;
                    if (hit.enabled) hit.down = true;
                }
                else if (popupOpen)
                {
                    FoodMenu = MountMenu = PetPanel = false;
                }
                else if (taming)
                {
                    // 미니게임 중에는 [교감!]만 받는다
                }
                else if (g.x < vw * 0.42f && g.y > VH * 0.3f && joyPtr == NoPtr)
                {
                    joyPtr = p.id;
                    joyCenter = g;
                    joyKnob = g;
                }
                else if (camPtr == NoPtr)
                {
                    camPtr = p.id;
                    camLast = g;
                    camStart = g;
                    camStartTime = Time.unscaledTime;
                }
            }
            else
            {
                if (p.id == joyPtr) joyKnob = g;
                if (p.id == camPtr)
                {
                    CamDelta += g - camLast;
                    camLast = g;
                }
            }

            if (p.ended)
            {
                if (p.id == joyPtr) joyPtr = NoPtr;
                if (p.id == camPtr)
                {
                    if ((g - camStart).magnitude < 14f && Time.unscaledTime - camStartTime < 0.35f) TapWorld(g);
                    camPtr = NoPtr;
                }
                foreach (var b in order) if (b.ptr == p.id) b.ptr = NoPtr;
            }
        }
    }

    void KeyboardMerge()
    {
        Press("jump", TouchInput.JumpDown, TouchInput.JumpHeld);
        Press("descend", false, TouchInput.DescendHeld);
        Press("attack", TouchInput.AttackDown, false);
        Press("ride", TouchInput.RideDown, false);
        Press("tame", TouchInput.TameDown, false);
        Press("feed", TouchInput.FeedDown, false);
        Press("target", TouchInput.TargetDown, false);
        Press("bond", TouchInput.BondDown, false);
    }

    void Press(string id, bool down, bool held)
    {
        var b = B(id);
        if (!b.visible || !b.enabled) return;
        if (down) b.down = true;
        if (held) b.held = true;
    }

    void TapWorld(Vector2 g)
    {
        var gm = GameManager.I;
        var cam = Camera.main;
        if (gm == null || cam == null) return;
        Monster best = null;
        float bd = 75f;
        foreach (var m in Monster.AllMonsters)
        {
            if (m.team != Team.Wild || m.IsDead) continue;
            if ((m.transform.position - gm.player.transform.position).sqrMagnitude > 70f * 70f) continue;
            Vector3 sp = cam.WorldToScreenPoint(m.AimPoint);
            if (sp.z < 0f) continue;
            Vector2 mg = new Vector2(sp.x, Screen.height - sp.y) / scale;
            float d = (mg - g).magnitude - 10f * m.def.size;
            if (d < bd)
            {
                bd = d;
                best = m;
            }
        }
        if (best != null) gm.SelectTarget(best);
    }

    // ───────────── 버튼 배치 ─────────────
    static string Short(string name)
    {
        int i = name.LastIndexOf(' ');
        return i >= 0 ? name.Substring(i + 1) : name;
    }

    static string SkillName(Role r)
    {
        switch (r)
        {
            case Role.Tank: return "도발";
            case Role.Support: return "치유";
            case Role.Ranged: return "연사";
            default: return "강타";
        }
    }

    void Layout()
    {
        var gm = GameManager.I;
        if (gm == null || gm.player == null) return;
        var pl = gm.player;
        float R = vw, Bt = VH;

        if (gm.taming.active)
        {
            Circle("bond", new Vector2(R * 0.5f, Bt - 140f), 85f, "교감!", new Color(1f, 0.5f, 0.72f, 0.92f), true, true);
            return;
        }

        Monster t = gm.target;
        float tDist = t != null ? Vector3.Distance(t.transform.position, pl.transform.position) : 999f;

        Circle("attack", new Vector2(R - 130f, Bt - 130f), 72f, "공격", new Color(0.85f, 0.3f, 0.3f, 0.82f));
        Circle("jump", new Vector2(R - 280f, Bt - 92f), 52f, pl.Flying ? "상승" : "점프", BaseC);
        if (pl.Flying) Circle("descend", new Vector2(R - 280f, Bt - 215f), 46f, "하강", BaseC);
        bool canTame = t != null && t.Tameable && tDist <= TamingSystem.TameRange;
        Circle("tame", new Vector2(R - 130f, Bt - 290f), 56f, "테이밍", canTame ? new Color(1f, 0.72f, 0.2f, 0.92f) : BaseC).highlight = canTame;
        Circle("feed", new Vector2(R - 410f, Bt - 100f), 46f, "먹이", BaseC, t != null && t.team == Team.Wild && tDist < 12f);
        Circle("ride", new Vector2(R - 410f, Bt - 225f), 46f, pl.Riding ? "내리기" : "탑승", new Color(0.25f, 0.5f, 0.85f, 0.82f));

        int slot = 0;
        foreach (var p in GameState.pets)
        {
            if (!p.inParty) continue;
            if (slot >= GameState.MaxParty) break;
            var m = p.instance;
            bool alive = m != null && m.gameObject.activeSelf && !m.IsDead;
            Color ec = GameDB.ElementColor(p.Def.element) * 0.65f;
            var b = Circle("skill" + slot, new Vector2(R - 130f - slot * 102f, Bt - 430f), 42f,
                           Short(p.Def.name) + "\n" + SkillName(p.Def.role), Util.WithA(ec, 0.85f), alive);
            b.fill = alive ? m.SkillReady01 : 0f;
            slot++;
        }

        Circle("mode", new Vector2(R - 60f, 55f), 40f, "지휘\n" + GameManager.ModeShort[gm.mode], BaseC);
        Circle("pets", new Vector2(R - 150f, 55f), 40f, "펫", BaseC);
        Circle("target", new Vector2(R - 240f, 55f), 40f, "타깃", BaseC);

        if (FoodMenu)
        {
            for (int i = 0; i < 4; i++)
            {
                Food f = (Food)i;
                int n = GameState.food[f];
                Circle("food" + i, new Vector2(R * 0.5f + (i - 1.5f) * 150f, Bt * 0.5f), 58f,
                       GameDB.FoodName(f) + "\nx" + n, new Color(0.35f, 0.25f, 0.15f, 0.92f), n > 0, true);
            }
        }
        if (MountMenu)
        {
            var list = gm.MountList();
            int n = Mathf.Min(5, list.Count);
            for (int i = 0; i < n; i++)
            {
                var d = list[i].Def;
                string sub = d.mount == MountType.Fly ? "비행 " + d.flyTier + "단계" : "지상";
                Circle("mount" + i, new Vector2(R * 0.5f + (i - (n - 1) * 0.5f) * 165f, Bt * 0.5f), 66f,
                       d.name + "\n" + sub, new Color(0.2f, 0.4f, 0.75f, 0.92f), list[i].reviveTimer <= 0f, true);
            }
        }
        if (PetPanel)
        {
            for (int i = 0; i < GameState.pets.Count && i < 8; i++)
            {
                var p = GameState.pets[i];
                var d = p.Def;
                string lbl = "Lv." + p.level + "  " + d.name + "   [" + GameDB.ElementName(d.element) + " · " + d.grade + "]"
                             + (d.mount == MountType.Fly ? "  · 비행 탈것" : d.mount == MountType.Ground ? "  · 지상 탈것" : "")
                             + (p.reviveTimer > 0f ? "  · 기절" : "")
                             + (p.inParty ? "      ✔ 출전 중" : "      대기 (펫 농장)");
                RectBtn("pet" + i, new Rect(R * 0.5f - 330f, 150f + i * 58f, 660f, 50f), lbl,
                        p.inParty ? new Color(0.2f, 0.45f, 0.3f, 0.95f) : new Color(0.2f, 0.2f, 0.28f, 0.95f));
            }
            RectBtn("petclose", new Rect(R * 0.5f + 250f, 92f, 80f, 46f), "  닫기", new Color(0.5f, 0.2f, 0.2f, 0.95f));
        }
    }

    // ───────────── 그리기 ─────────────
    void OnGUI()
    {
        if (Event.current.type != EventType.Repaint) return;
        var gm = GameManager.I;
        if (gm == null || gm.player == null) return;
        if (style == null)
        {
            style = new GUIStyle(GUI.skin.label);
            style.fontStyle = FontStyle.Bold;
            style.wordWrap = true;
            style.clipping = TextClipping.Overflow;
        }
        GUI.matrix = Matrix4x4.TRS(Vector3.zero, Quaternion.identity, new Vector3(scale, scale, 1f));

        DrawWorld(gm);
        DrawStatus(gm);
        DrawTarget(gm);
        DrawQuest(gm);
        if (!gm.taming.active) DrawJoystick();
        foreach (var b in order) if (b.visible && !b.popup) DrawBtn(b);

        bool popupOpen = FoodMenu || MountMenu || PetPanel;
        if (popupOpen)
        {
            Fill(new Rect(0f, 0f, vw, VH), new Color(0f, 0f, 0f, 0.5f));
            string title = FoodMenu ? "줄 먹이를 고르세요" : MountMenu ? "탈것을 고르세요" : "보유 펫 — 눌러서 출전/대기 전환 (최대 3마리)";
            Text(new Rect(0f, PetPanel ? 100f : VH * 0.5f - 130f, vw, 34f), title, 24, Color.white, TextAnchor.MiddleCenter);
        }
        foreach (var b in order) if (b.visible && b.popup) DrawBtn(b);
        if (gm.taming.active) DrawMinigame(gm);
        DrawToasts();
    }

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
        style.normal.textColor = new Color(0f, 0f, 0f, 0.75f * c.a);
        GUI.Label(new Rect(r.x + 1.5f, r.y + 1.5f, r.width, r.height), s, style);
        style.normal.textColor = c;
        GUI.Label(r, s, style);
    }

    void Bar(Rect r, float v, Color fg, bool tick30 = false)
    {
        Fill(r, new Color(0f, 0f, 0f, 0.55f));
        Fill(new Rect(r.x + 2f, r.y + 2f, (r.width - 4f) * Mathf.Clamp01(v), r.height - 4f), fg);
        if (tick30) Fill(new Rect(r.x + 2f + (r.width - 4f) * 0.3f - 1f, r.y, 2f, r.height), Gold);
    }

    void DrawBtn(VBtn b)
    {
        Color col = b.enabled ? b.color : new Color(0.3f, 0.3f, 0.3f, 0.45f);
        if (b.ptr != NoPtr) col = Color.Lerp(col, Color.white, 0.25f);
        if (b.rect)
        {
            Fill(b.box, col);
            Text(new Rect(b.box.x + 14f, b.box.y, b.box.width - 20f, b.box.height), b.label, 19, Color.white, TextAnchor.MiddleLeft);
            return;
        }
        Rect r = new Rect(b.c.x - b.r, b.c.y - b.r, b.r * 2f, b.r * 2f);
        if (b.highlight)
        {
            float g = b.r * (1.18f + Mathf.Sin(Time.time * 6f) * 0.06f);
            GUI.color = Util.WithA(Gold, 0.85f);
            GUI.DrawTexture(new Rect(b.c.x - g, b.c.y - g, g * 2f, g * 2f), ringTex);
        }
        GUI.color = col;
        GUI.DrawTexture(r, circleTex);
        if (b.fill < 0.999f)
        {
            GUI.BeginGroup(new Rect(r.x, r.y, r.width, r.height * (1f - b.fill)));
            GUI.color = new Color(0f, 0f, 0f, 0.55f);
            GUI.DrawTexture(new Rect(0f, 0f, r.width, r.height), circleTex);
            GUI.EndGroup();
        }
        GUI.color = new Color(1f, 1f, 1f, 0.35f);
        GUI.DrawTexture(r, ringTex);
        GUI.color = Color.white;
        int size = b.r > 60f ? 26 : b.r > 45f ? 20 : 15;
        Text(r, b.label, size, b.enabled ? Color.white : new Color(0.8f, 0.8f, 0.8f, 0.7f), TextAnchor.MiddleCenter);
    }

    void DrawJoystick()
    {
        Vector2 c = joyPtr != NoPtr ? joyCenter : new Vector2(175f, VH - 170f);
        Vector2 k = joyPtr != NoPtr ? joyCenter + Vector2.ClampMagnitude(joyKnob - joyCenter, JoyR) : c;
        float a = joyPtr != NoPtr ? 0.6f : 0.3f;
        GUI.color = new Color(1f, 1f, 1f, a);
        GUI.DrawTexture(new Rect(c.x - JoyR, c.y - JoyR, JoyR * 2f, JoyR * 2f), ringTex);
        GUI.color = new Color(1f, 1f, 1f, a * 0.8f);
        GUI.DrawTexture(new Rect(k.x - 40f, k.y - 40f, 80f, 80f), circleTex);
        GUI.color = Color.white;
    }

    bool ToGui(Camera cam, Vector3 world, out Vector2 g)
    {
        Vector3 sp = cam.WorldToScreenPoint(world);
        g = new Vector2(sp.x, Screen.height - sp.y) / scale;
        return sp.z > 0f;
    }

    void DrawWorld(GameManager gm)
    {
        var cam = Camera.main;
        if (cam == null) return;
        Vector2 g;

        foreach (var m in Monster.AllMonsters)
        {
            if (m.IsDead) continue;
            if ((m.transform.position - cam.transform.position).sqrMagnitude > 50f * 50f) continue;
            if (!ToGui(cam, m.AimPoint + Vector3.up * (0.6f * m.def.size + 0.3f), out g)) continue;
            bool wild = m.team == Team.Wild;
            bool sel = m == gm.target;
            Bar(new Rect(g.x - 32f, g.y, 64f, 9f), m.hp / m.maxHp,
                !wild ? new Color(0.4f, 0.9f, 0.4f) : m.Tameable ? Gold : new Color(0.95f, 0.3f, 0.3f), wild);
            if (wild)
            {
                Text(new Rect(g.x - 90f, g.y - 24f, 180f, 22f), "Lv." + m.level + " " + m.def.name, 14,
                     sel ? Gold : Color.white, TextAnchor.MiddleCenter);
                if (m.Tameable)
                    Text(new Rect(g.x - 90f, g.y - 46f, 180f, 22f), "★ 테이밍 가능", 15,
                         Util.WithA(Gold, 0.6f + 0.4f * Mathf.Abs(Mathf.Sin(Time.time * 5f))), TextAnchor.MiddleCenter);
                if (sel)
                    Text(new Rect(g.x - 20f, g.y - (m.Tameable ? 76f : 56f), 40f, 30f), "▼", 24, Gold, TextAnchor.MiddleCenter);
            }
        }

        foreach (var p in pops)
        {
            if (!ToGui(cam, p.pos + Vector3.up * p.t * 1.6f, out g)) continue;
            float a = 1f - Mathf.Clamp01((p.t - 0.7f) / 0.5f);
            Text(new Rect(g.x - 120f, g.y - 14f, 240f, 28f), p.text, p.big ? 22 : 17, Util.WithA(p.color, a), TextAnchor.MiddleCenter);
        }

        if (gm.HasQuestPos)
        {
            Vector3 qp = gm.QuestPos + Vector3.up * 2f;
            float dist = Vector3.Distance(qp, gm.player.transform.position);
            if (dist > 10f)
            {
                bool front = ToGui(cam, qp, out g);
                if (!front) g = new Vector2(vw - g.x, VH - 70f);
                g.x = Mathf.Clamp(g.x, 40f, vw - 40f);
                g.y = Mathf.Clamp(g.y, 120f, VH - 50f);
                Text(new Rect(g.x - 20f, g.y - 18f, 40f, 36f), "◆", 26, Gold, TextAnchor.MiddleCenter);
                Text(new Rect(g.x - 50f, g.y + 14f, 100f, 22f), Mathf.RoundToInt(dist) + "m", 15, Gold, TextAnchor.MiddleCenter);
            }
        }
    }

    void DrawStatus(GameManager gm)
    {
        var pl = gm.player;
        Text(new Rect(20f, 8f, 330f, 24f), "테이머   " + Mathf.CeilToInt(pl.hp) + " / " + Mathf.RoundToInt(pl.maxHp), 16, Color.white, TextAnchor.MiddleLeft);
        Bar(new Rect(20f, 32f, 330f, 18f), pl.hp / pl.maxHp, new Color(0.4f, 0.9f, 0.45f));
        float y = 56f;
        if (pl.Riding)
        {
            var d = pl.mount.Def;
            string s = "탑승: " + d.name;
            if (pl.Flying)
                s += "   고도 " + Mathf.RoundToInt(pl.transform.position.y) + "m / 최고 " + Mathf.RoundToInt(GameDB.FlyCeiling(d.flyTier)) + "m";
            Text(new Rect(20f, y, 420f, 22f), s, 15, new Color(0.7f, 0.9f, 1f), TextAnchor.MiddleLeft);
            y += 24f;
            if (pl.Flying)
            {
                Bar(new Rect(20f, y, 330f, 12f), pl.stamina / pl.maxStamina, new Color(0.4f, 0.85f, 1f));
                y += 18f;
            }
        }
        y += 6f;
        foreach (var p in GameState.pets)
        {
            if (!p.inParty) continue;
            var m = p.instance;
            string st = p.reviveTimer > 0f ? "  기절 " + Mathf.CeilToInt(p.reviveTimer) + "초" : (pl.mount == p ? "  탑승 중" : "");
            Text(new Rect(20f, y, 330f, 20f), "Lv." + p.level + " " + p.Def.name + st, 14, Color.white, TextAnchor.MiddleLeft);
            float v = (m != null && p.reviveTimer <= 0f) ? m.hp / m.maxHp : 0f;
            Bar(new Rect(20f, y + 20f, 200f, 9f), v, new Color(0.4f, 0.9f, 0.4f));
            y += 36f;
        }
        Text(new Rect(20f, y + 2f, 420f, 20f),
             "먹이  젤리 " + GameState.food[Food.Jelly] + " · 생고기 " + GameState.food[Food.Meat] +
             " · 씨앗 " + GameState.food[Food.Seed] + " · 열매 " + GameState.food[Food.Berry],
             13, new Color(0.9f, 0.85f, 0.7f), TextAnchor.MiddleLeft);
    }

    void DrawTarget(GameManager gm)
    {
        var t = gm.target;
        if (t == null) return;
        Rect r = new Rect(vw * 0.5f - 220f, 10f, 440f, 104f);
        Fill(r, new Color(0f, 0f, 0f, 0.55f));
        Text(new Rect(r.x + 12f, r.y + 4f, 416f, 24f),
             "Lv." + t.level + " " + t.def.name + "   [" + GameDB.ElementName(t.element) + " · " + t.def.grade + "]",
             18, Color.white, TextAnchor.MiddleLeft);
        Bar(new Rect(r.x + 12f, r.y + 32f, 416f, 16f), t.hp / t.maxHp, t.Tameable ? Gold : new Color(0.95f, 0.3f, 0.3f), true);
        string line = t.Tameable
            ? "★ 테이밍 가능!  예상 성공률 " + Mathf.RoundToInt(gm.taming.BaseChance(t, 0f) * 100f) + "% (+교감 보너스)"
            : "체력을 금색 선(30%) 아래로 깎으면 테이밍 가능";
        Text(new Rect(r.x + 12f, r.y + 52f, 416f, 22f), line, 15, t.Tameable ? Gold : new Color(0.85f, 0.85f, 0.85f), TextAnchor.MiddleLeft);
        string fav = GameDB.RevealedFavorites.Contains(t.def.id) ? GameDB.FoodName(t.def.favorite) : "???";
        Text(new Rect(r.x + 12f, r.y + 76f, 416f, 22f),
             "좋아하는 먹이: " + fav + (t.fedFavorite ? " (먹임 ♥)" : "") + "    호감도 +" + Mathf.RoundToInt(GameState.Fondness(t.def.id) * 100f) + "%",
             14, new Color(0.8f, 0.8f, 0.8f), TextAnchor.MiddleLeft);
    }

    void DrawQuest(GameManager gm)
    {
        Rect r = new Rect(vw - 330f, 104f, 310f, 64f);
        Fill(r, new Color(0f, 0f, 0f, 0.45f));
        Text(new Rect(r.x + 10f, r.y + 2f, 295f, 60f), gm.QuestText, 14, new Color(1f, 0.93f, 0.7f), TextAnchor.MiddleLeft);
    }

    void DrawMinigame(GameManager gm)
    {
        var tm = gm.taming;
        var m = tm.target;
        if (m == null) return;
        Fill(new Rect(0f, 0f, vw, VH), new Color(0f, 0f, 0f, 0.35f));
        Rect panel = new Rect(vw * 0.5f - 320f, 140f, 640f, 250f);
        Fill(panel, new Color(0.08f, 0.08f, 0.14f, 0.9f));
        Text(new Rect(panel.x, panel.y + 12f, panel.width, 32f), Util.EulReul(m.def.name) + " 길들이는 중…", 24, Color.white, TextAnchor.MiddleCenter);
        Text(new Rect(panel.x, panel.y + 48f, panel.width, 24f), "바늘이 분홍 칸에 들어왔을 때 [교감!]   (금색 칸 = 완벽)", 16,
             new Color(0.85f, 0.85f, 0.85f), TextAnchor.MiddleCenter);

        Rect bar = new Rect(panel.x + 40f, panel.y + 100f, panel.width - 80f, 44f);
        Fill(bar, new Color(0.2f, 0.2f, 0.25f, 1f));
        Fill(new Rect(bar.x + (tm.zoneCenter - tm.zoneHalf) * bar.width, bar.y, tm.zoneHalf * 2f * bar.width, bar.height), new Color(1f, 0.45f, 0.7f));
        Fill(new Rect(bar.x + (tm.zoneCenter - tm.perfectHalf) * bar.width, bar.y, tm.perfectHalf * 2f * bar.width, bar.height), Gold);
        Fill(new Rect(bar.x + tm.needle * bar.width - 3f, bar.y - 10f, 6f, bar.height + 20f), Color.white);

        string extra = (m.fedFavorite ? "먹이 보너스 +20%   " : "") +
                       (GameState.Fondness(m.def.id) > 0f ? "호감도 +" + Mathf.RoundToInt(GameState.Fondness(m.def.id) * 100f) + "%" : "");
        Text(new Rect(panel.x, panel.y + 162f, panel.width, 24f),
             "남은 시간 " + tm.timeLeft.ToString("0.0") + "초      기본 성공률 " + Mathf.RoundToInt(tm.BaseChance(m, 0f) * 100f) + "%",
             17, Color.white, TextAnchor.MiddleCenter);
        if (extra.Length > 0)
            Text(new Rect(panel.x, panel.y + 194f, panel.width, 24f), extra, 15, Gold, TextAnchor.MiddleCenter);
    }

    void DrawToasts()
    {
        float y = 124f;
        foreach (var t in toasts)
        {
            float a = Mathf.Clamp01((t.life - t.t) / 0.5f);
            Rect r = new Rect(vw * 0.5f - 310f, y, 620f, 34f);
            Fill(r, new Color(0f, 0f, 0f, 0.5f * a));
            Text(r, t.text, 16, new Color(1f, 1f, 1f, a), TextAnchor.MiddleCenter);
            y += 38f;
        }
    }
}
