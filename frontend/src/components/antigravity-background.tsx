"use client";

import { useEffect, useRef } from "react";

export function AntigravityBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    let frame = 0;
    let width = 0;
    let height = 0;
    const particles = Array.from({ length: 56 }, (_, index) => ({
      x: (index * 83) % 1000,
      y: (index * 47) % 700,
      speed: 0.08 + (index % 4) * 0.02,
      radius: index % 7 === 0 ? 1.25 : 0.8,
    }));

    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = () => {
      context.clearRect(0, 0, width, height);
      particles.forEach((particle, index) => {
        particle.y -= particle.speed;
        if (particle.y < -8) particle.y = height + 8;
        const x = (particle.x / 1000) * width + Math.sin(frame / 1700 + index) * 7;
        context.beginPath();
        context.arc(x, particle.y, particle.radius, 0, Math.PI * 2);
        context.fillStyle = "rgba(124, 158, 255, 0.16)";
        context.fill();
      });
      frame = window.requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="relay-landing-particles" aria-hidden="true" />;
}
