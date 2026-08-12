#version 330

#moj_import <minecraft:fog.glsl>
#moj_import <minecraft:dynamictransforms.glsl>

uniform sampler2D Sampler0;

in float sphericalVertexDistance;
in float cylindricalVertexDistance;
in vec2 texCoord0;
in vec4 vertexColor;
in vec4 particleColor;

out vec4 fragColor;

bool isMeteorParticle(vec3 color) {
    // Java가 원래 DUST 색의 각 채널 하위 4비트에 (12, 8, 7)을 심는다.
    // 원본 색 자체를 유지하므로 셰이더가 적용되지 않아도 파란 마커가 노출되지 않는다.
    vec3 channel = floor(color * 255.0 + 0.5);
    return mod(channel.r, 16.0) == 12.0
        && mod(channel.g, 16.0) == 8.0
        && mod(channel.b, 16.0) == 7.0;
}

void main() {
    vec4 tex = texture(Sampler0, texCoord0);
    vec4 color = tex * vertexColor * ColorModulator;
    if (color.a < 0.1) {
        discard;
    }

    if (isMeteorParticle(particleColor.rgb)) {
        // 유성우만 lightmap을 무시하고 원래 색을 밝게 만든다. 안개는 유지한다.
        color.rgb = clamp(tex.rgb * particleColor.rgb * ColorModulator.rgb * 1.35,
                          0.0, 1.0);
    }

    // 유성우 이외에는 1.21.11 바닐라 particle.fsh와 동일한 경로.
    fragColor = apply_fog(color, sphericalVertexDistance, cylindricalVertexDistance,
                          FogEnvironmentalStart, FogEnvironmentalEnd,
                          FogRenderDistanceStart, FogRenderDistanceEnd, FogColor);
}
