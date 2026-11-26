using UnityEngine;

namespace Necro
{
    // 광원 하나의 '끄는 거리' 덮어쓰기. LightCuller 는 보통 빛 범위(range) × rangeFactor 에서 광원을 끄지만,
    // 이 컴포넌트가 붙은 광원은 far(m)에서 끈다 (minRadius ~ maxRadius 안으로 자른다).
    // 장면·장소의 '등대 빛'(화로·영혼 수정·모닥불·길가 사당·작은 납골당, 장면을 떠도는 영혼 빛)이 멀리서도 보이게 하려고 쓴다.
    // 거꾸로 기본보다 짧게도 쓴다: 수정 무리 곁의 작은 영혼 수정은 45 m (등대 빛은 큰 수정 하나만, 광원 예산을 아낀다).
    // Light.range 는 그대로라 비추는 넓이와 그리기 비용은 늘지 않는다 (켜 둘 후보 수만 조금 는다).
    // 월드 도구가 붙인다: objects.json lights 의 "far", 소품 META.light 의 "far" (Tools/WorldGen/SPEC.md).
    // LightCuller 는 Refresh 때 한 번 읽는다 (실행 중에 값을 바꾸면 LightCuller.Refresh 를 다시 부른다).
    [DisallowMultipleComponent]
    public class LightCullDistance : MonoBehaviour
    {
        [Header("끄는 거리")]
        [Tooltip("이 광원을 끄는 거리 (m). 0 이면 LightCuller 기본 규칙 (range × rangeFactor). 등대 빛은 140 m 안팎")]
        [Min(0f)] public float far = 140f;
    }
}
