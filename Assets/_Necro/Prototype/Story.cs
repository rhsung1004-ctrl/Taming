using System.Collections.Generic;

namespace Necro.Proto
{
    // 프로토타입 대사. 2D판(사령술사 키우기) data/story.gd 의 1·2장 대사를 바탕으로 하고,
    // 본드래곤처럼 3D판에만 있는 장면은 새로 썼다. 한 번 나온 대사는 다시 나오지 않는다.
    // 말하는 이: "me" = 주인공, "narr" = 해설, 그 밖에는 유닛 id.
    public static class Story
    {
        static readonly HashSet<string> seen = new HashSet<string>();

        static readonly Dictionary<string, string[,]> Lines = new Dictionary<string, string[,]>
        {
            { "r1_enter", new[,] {
                { "narr", "차가운 흙 아래에서 눈을 떴다. 얼마나 잠들어 있었을까." },
                { "me", "…봉인이 풀렸네. 몸은 무겁지만, 망자들의 목소리는 그대로 들려." } } },
            { "first_raise", new[,] {
                { "me", "잘 왔어. 오늘부터 너희는 내 군단이야. 내 뒤로 오렴." } } },
            { "r1_hero", new[,] {
                { "boss", "누가 감히 묘지의 잠을 깨우는가! 이곳의 시체는 모두 내 것이다!" },
                { "me", "시체에게 주인이 어디 있어. 부르는 자를 따를 뿐이지." } } },
            { "keeper_raise", new[,] {
                { "me", "네 묘지를 어지럽혀서 미안해. …같이 가 줄래?" },
                { "boss", "…부르는 자를… 따를 뿐…" },
                { "me", "고마워. 묘지는 이제 같이 지키자." } } },
            { "tier1", new[,] {
                { "me", "…기억났어. 화살 한 발로 싸우던 건 여기까지야." } } },
            { "r2_enter", new[,] {
                { "narr", "한때 사령술사들의 도시였던 곳. 이제는 잿빛 돌무더기만 남았다." },
                { "me", "기억나. 여기서 처음 망자를 일으켰지. …다 무너졌구나." } } },
            { "dragon_meet", new[,] {
                { "narr", "뼈 무덤 한가운데에서, 잠들지 못한 고룡이 고개를 든다." },
                { "me", "오래 혼자 깨어 있었구나. 내가 재워 줄게." } } },
            { "tier2", new[,] {
                { "me", "왕관이 응답하고 있어. 금주의 봉인도 풀렸네." } } },
            { "dragon_raise", new[,] {
                { "narr", "고룡의 뼈가, 내민 손끝으로 천천히 고개를 숙인다." },
                { "me", "내 뒤로 오렴. 오늘부터 네가 내 날개야." } } },
            { "sky_enter", new[,] {
                { "narr", "하늘에 떠 있는 부서진 성채. 왕관 조각의 기운이 여기서 흘러나온다." },
                { "me", "죽음의 왕의 병사들이네. 비켜 주면 좋겠는데, 그럴 리 없겠지." } } },
            { "r1_boss", new[,] {
                { "lord", "그 기운… 설마, 봉인된 사령술사가 깨어났단 말인가." },
                { "lord", "죽음의 왕께서 내리신 왕관 조각은 넘겨줄 수 없다!" },
                { "me", "넘겨 달라고 한 적 없어. 가져갈 거야." } } },
            { "lord_raise", new[,] {
                { "narr", "쓰러진 군주의 갑옷 틈으로, 꺼져 가던 불빛이 내민 손을 올려다본다." },
                { "me", "남의 왕관을 지키느라 고생했어. 이제 네 이름으로 싸우렴." },
                { "lord", "…명을… 내리소서…" } } },
            { "r1_clear", new[,] {
                { "me", "첫 번째 조각… 아직 따뜻하네." },
                { "narr", "부서진 '망자의 왕관' 조각이 손끝에서 희미하게 빛난다. 나머지 아홉 조각이 어딘가에서 응답하고 있다." },
                { "me", "나를 봉인하고 왕관을 부순 자. 죽음의 왕… 기다려." } } },
        };

        public static void Reset() { seen.Clear(); }

        public static void Play(string key)
        {
            if (!seen.Add(key)) return;
            string[,] l;
            if (!Lines.TryGetValue(key, out l)) return;
            for (int i = 0; i < l.GetLength(0); i++) Hud.Say(l[i, 0], l[i, 1]);
        }
    }
}
