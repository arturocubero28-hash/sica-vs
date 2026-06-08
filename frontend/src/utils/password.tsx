// Política de contraseñas (debe coincidir con el backend)
export function passwordValida(p: string): boolean {
  return p.length >= 8 && /[A-Z]/.test(p) && /[^A-Za-z0-9]/.test(p);
}

export function RequisitosPassword({ password }: { password: string }) {
  const reqs = [
    { ok: password.length >= 8, txt: "Al menos 8 caracteres" },
    { ok: /[A-Z]/.test(password), txt: "Una letra mayúscula" },
    { ok: /[^A-Za-z0-9]/.test(password), txt: "Un signo (! @ # $ % & *)" },
  ];
  return (
    <div className="req-password">
      {reqs.map((r, i) => (
        <div key={i} className={`req-item ${r.ok ? "ok" : ""}`}>
          <span>{r.ok ? "✓" : "○"}</span> {r.txt}
        </div>
      ))}
    </div>
  );
}
