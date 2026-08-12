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

vec3 meteorColor(float f) {
    f = clamp(f, 0.0, 1.0);
    if (f < 0.08) {
        return mix(vec3(1.0, 120.0 / 255.0, 60.0 / 255.0),
                   vec3(1.0, 190.0 / 255.0, 90.0 / 255.0), f / 0.08);
    }
    if (f < 0.18) {
        return mix(vec3(1.0, 190.0 / 255.0, 90.0 / 255.0),
                   vec3(1.0, 240.0 / 255.0, 180.0 / 255.0), (f - 0.08) / 0.10);
    }
    if (f < 0.35) {
        return mix(vec3(1.0, 240.0 / 255.0, 180.0 / 255.0),
                   vec3(245.0 / 255.0, 250.0 / 255.0, 240.0 / 255.0), (f - 0.18) / 0.17);
    }
    if (f < 0.60) {
        return mix(vec3(245.0 / 255.0, 250.0 / 255.0, 240.0 / 255.0),
                   vec3(140.0 / 255.0, 195.0 / 255.0, 1.0), (f - 0.35) / 0.25);
    }
    return mix(vec3(140.0 / 255.0, 195.0 / 255.0, 1.0),
               vec3(120.0 / 255.0, 90.0 / 255.0, 215.0 / 255.0), (f - 0.60) / 0.40);
}

bool isMeteorParticle(vec3 color) {
    // Java RegionParticleTask가 보내는 전용 마커: R=1, B=255, G=f.
    return color.r < 0.01 && color.b > 0.99;
}

void main() {
    vec4 tex = texture(Sampler0, texCoord0);
    vec4 color = tex * vertexColor * ColorModulator;
    if (color.a < 0.1) {
        discard;
    }

    if (isMeteorParticle(particleColor.rgb)) {
        // 유성우만 lightmap을 무시하고 밝게 복원한다. 안개는 유지해 하늘과 자연스럽게 섞인다.
        color.rgb = clamp(tex.rgb * meteorColor(particleColor.g) * ColorModulator.rgb * 1.35,
                          0.0, 1.0);
    }

    // 유성우 이외에는 1.21.11 바닐라 particle.fsh와 동일한 경로.
    fragColor = apply_fog(color, sphericalVertexDistance, cylindricalVertexDistance,
                          FogEnvironmentalStart, FogEnvironmentalEnd,
                          FogRenderDistanceStart, FogRenderDistanceEnd, FogColor);
}
