#version 150

uniform sampler2D Sampler0;

in vec2 texCoord0;
in vec4 vertexColor;

out vec4 fragColor;

void main() {
    vec4 tex = texture(Sampler0, texCoord0);

    float alpha = tex.a * vertexColor.a;
    if (alpha < 0.1) {
        discard;
    }

    vec3 rgb = tex.rgb * vertexColor.rgb;

    rgb = clamp(rgb * 1.35, 0.0, 1.0);

    fragColor = vec4(rgb, alpha);
}
