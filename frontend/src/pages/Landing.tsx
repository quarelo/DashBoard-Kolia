import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  ArrowRight, CheckCircle2, ChevronRight, Star,
  FileText, Brain, Sparkles, BarChart3,
  TrendingDown, Target, Package, Heart,
  Shield, Clock, Users, Zap, LineChart,
  Play, BrainCircuit,
} from "lucide-react";
import { KoliaLogo } from "../components/ui/KoliaLogo";

/* ─── data ─────────────────────────────────────────────────── */
const navLinks = [
  { href: "#problema",    label: "Problema" },
  { href: "#solucao",     label: "Solução" },
  { href: "#beneficios",  label: "Benefícios" },
  { href: "#resultados",  label: "Resultados" },
];

const problemItems = [
  { emoji: "📋", title: "Reuniões sem valor capturado", desc: "Horas de conversas estratégicas viram notas dispersas em e-mails, PDFs e anotações pessoais que nunca chegam ao CRM." },
  { emoji: "⚠️", title: "Churn detectado tarde demais", desc: "Sinais de insatisfação aparecem nas transcrições semanas antes do cliente pedir cancelamento — mas ninguém analisa." },
  { emoji: "💸", title: "Oportunidades que escapam", desc: "O cliente menciona uma necessidade latente. O vendedor não documenta. A oportunidade de upsell some no esquecimento." },
  { emoji: "📊", title: "Gestão no escuro", desc: "Diretores tomam decisões sem visibilidade real do que é dito nas dezenas de reuniões que acontecem por semana." },
];

const steps = [
  { number: "01", icon: FileText,  title: "Transcrições das reuniões",  desc: "Carregue transcrições de Zoom, Teams, Meet ou CSV/XLSX. A plataforma aceita qualquer formato." },
  { number: "02", icon: Brain,     title: "Processamento com IA",       desc: "LLMs de última geração analisam cada frase, identificando sentimentos, riscos e intenções comerciais." },
  { number: "03", icon: Sparkles,  title: "Geração de insights",        desc: "Insights categorizados por tipo e prioridade, com evidências diretas extraídas da transcrição." },
  { number: "04", icon: BarChart3, title: "Dashboard executivo",        desc: "Visualizações interativas e recomendações acionáveis — prontas para o time comercial agir." },
];

const benefits = [
  { icon: TrendingDown, bg: "bg-rose-50",    color: "text-rose-500",    title: "Redução de Churn",            desc: "Detecte insatisfação antes do cancelamento. Aja com antecedência e retenha contratos estratégicos." },
  { icon: Target,       bg: "bg-brand/8",    color: "text-brand",       title: "Receita de Upsell",           desc: "Oportunidades de expansão emergem das próprias conversas. Transforme reuniões em pipeline qualificado." },
  { icon: Package,      bg: "bg-violet-50",  color: "text-violet-600",  title: "Inteligência de Produto",     desc: "Feedbacks de produto consolidados de dezenas de clientes viram input direto para o roadmap." },
  { icon: Heart,        bg: "bg-pink-50",    color: "text-pink-500",    title: "Sentimento em tempo real",    desc: "Monitore o humor dos seus clientes ao longo do tempo antes que impacte NPS e renovações." },
];

const differentials = [
  { icon: BrainCircuit, title: "IA Generativa",         desc: "LLMs treinados para contexto corporativo B2B. Capturam nuances, ironias e subtexto comercial." },
  { icon: Shield,       title: "Privacidade e LGPD",    desc: "Dados processados conforme LGPD. Infraestrutura certificada, sem armazenamento de áudio." },
  { icon: Clock,        title: "Análise em segundos",   desc: "Da transcrição ao insight completo em menos de 60 segundos. Sem filas, sem espera." },
  { icon: Users,        title: "Para times comerciais", desc: "Construído para CSMs, AEs e Diretores Comerciais. Não para engenheiros de dados." },
  { icon: Zap,          title: "Integração simples",    desc: "Funciona com CSV e XLSX hoje. APIs e webhooks disponíveis para integração completa." },
  { icon: LineChart,    title: "ROI mensurável",        desc: "Rastreie o impacto de cada insight em receita retida e oportunidades geradas." },
];

const metrics = [
  { value: "500+",   label: "Reuniões analisadas",     sub: "nos últimos 30 dias" },
  { value: "R$ 3.2M", label: "Pipeline gerado via IA", sub: "em oportunidades qualificadas" },
  { value: "404",    label: "Riscos detectados",       sub: "com ação preventiva" },
  { value: "87%",    label: "Precisão dos insights",   sub: "validada pelos times de CS" },
];

const testimonials = [
  { name: "Ana Ribeiro",    role: "VP de Tecnologia",   company: "Grupo Vivo",             text: "A KOLIA transformou a forma como nossa equipe processa reuniões. O que levava dias é entregue em minutos, com precisão cirúrgica.", rating: 5 },
  { name: "Roberto Alves",  role: "CFO",                company: "Petrobras Distribuidora", text: "Identificamos uma oportunidade de R$ 3M em automação fiscal diretamente de um QBR. O ROI foi imediato e inegável.", rating: 5 },
  { name: "Rodrigo Campos", role: "CTO",                company: "WEG Equipamentos",        text: "A IA captou nuances que um analista humano demoraria semanas para encontrar. Isso mudou como gerenciamos o relacionamento.", rating: 5 },
];

const clients = ["Vivo", "Petrobras", "Ambev", "Embraer", "Vale", "Bradesco", "Natura", "WEG"];

/* ─── mock dashboard preview ──────────────────────────────── */
function DashboardPreview() {
  return (
    <div className="bg-[#111827] rounded-2xl overflow-hidden shadow-2xl border border-white/10 w-full">
      {/* Browser chrome */}
      <div className="flex items-center gap-2 px-4 py-3 bg-[#0a0f1e] border-b border-white/8">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-400" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
        </div>
        <div className="flex-1 mx-3 bg-white/5 rounded px-3 py-1 text-xs text-slate-500 font-mono">
          kolia.totvs.com.br/app/dashboard
        </div>
      </div>

      {/* Sidebar + content */}
      <div className="flex">
        {/* Micro sidebar */}
        <div className="w-10 bg-[#0f172a] flex flex-col items-center py-3 gap-3 border-r border-white/8">
          {["", "", "", ""].map((_, i) => (
            <div
              key={i}
              className={`w-5 h-5 rounded ${i === 0 ? "bg-brand" : "bg-white/10"}`}
            />
          ))}
        </div>

        {/* Main */}
        <div className="flex-1 p-4">
          {/* KPIs */}
          <div className="grid grid-cols-4 gap-2 mb-3">
            {[
              { label: "Reuniões", value: "500", color: "#E76B38" },
              { label: "Em Risco", value: "3",   color: "#ef4444" },
              { label: "Oportunidades", value: "47",  color: "#22c55e" },
              { label: "NPS Médio", value: "72",  color: "#8b5cf6" },
            ].map((k) => (
              <div key={k.label} className="bg-white/5 rounded-lg p-2.5">
                <p className="text-[9px] text-slate-500 mb-1">{k.label}</p>
                <p className="text-lg font-black" style={{ color: k.color }}>{k.value}</p>
              </div>
            ))}
          </div>

          {/* Chart area */}
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2 bg-white/5 rounded-lg p-3 h-24 flex items-end gap-1">
              {[30, 50, 38, 65, 52, 72, 60, 80, 68, 85, 74, 90].map((h, i) => (
                <div
                  key={i}
                  className="flex-1 rounded-t-sm"
                  style={{
                    height: `${h}%`,
                    background: i % 3 === 0 ? "#E76B38" : `rgba(231,107,56,${0.2 + h * 0.004})`,
                  }}
                />
              ))}
            </div>
            <div className="bg-white/5 rounded-lg p-3 flex items-center justify-center">
              <div className="relative w-14 h-14">
                <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                  <circle cx="18" cy="18" r="14" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="4" />
                  <circle cx="18" cy="18" r="14" fill="none" stroke="#E76B38" strokeWidth="4"
                    strokeDasharray={`${60 * 0.88} 100`} strokeLinecap="round" />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xs font-black text-white">60%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── component ─────────────────────────────────────────────── */
export function Landing() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const goDash = () => navigate(user ? "/app/dashboard" : "/login");

  return (
    <div className="min-h-screen bg-white font-sans text-ink overflow-x-hidden">

      {/* ── Navbar ─────────────────────────────────────────────── */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-white/95 backdrop-blur-md border-b border-surface-border">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
          <KoliaLogo variant="horizontal-dark" height={26} />

          <div className="hidden md:flex items-center gap-7">
            {navLinks.map((l) => (
              <a key={l.href} href={l.href}
                className="text-sm font-medium text-ink-secondary hover:text-ink transition-colors">
                {l.label}
              </a>
            ))}
          </div>

          <button
            onClick={goDash}
            className="btn-primary"
          >
            Conhecer Plataforma
            <ChevronRight size={14} />
          </button>
        </div>
      </nav>

      {/* ── Hero ───────────────────────────────────────────────── */}
      <section className="relative pt-28 pb-20 px-6 overflow-hidden">
        {/* BG decoration */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#FEF3EE]/60 via-white to-white pointer-events-none" />
        <div className="absolute top-0 right-0 w-[700px] h-[700px] bg-brand/5 rounded-full blur-3xl pointer-events-none -translate-y-1/2 translate-x-1/3" />

        <div className="relative max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-14 items-center">
            {/* Left — copy */}
            <div>
              {/* Eyebrow */}
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-brand/8 border border-brand/20 rounded-full text-brand text-xs font-semibold mb-7">
                <Sparkles size={12} />
                Powered by AI · Plataforma de Inteligência Comercial
              </div>

              <h1 className="text-[2.75rem] md:text-5xl font-extrabold text-ink leading-[1.1] tracking-tight mb-6 text-balance">
                Transformando reuniões em{" "}
                <span className="text-brand">inteligência de negócio</span>
              </h1>

              <p className="text-lg text-ink-secondary leading-relaxed mb-8 max-w-lg">
                A plataforma que utiliza Inteligência Artificial para transformar transcrições de reuniões em oportunidades comerciais, alertas de churn e recomendações estratégicas.
              </p>

              <div className="flex flex-wrap gap-3 mb-10">
                <button onClick={goDash} className="btn-primary text-base px-7 py-3">
                  Conhecer Plataforma
                  <ArrowRight size={16} />
                </button>
                <button className="btn-ghost text-base px-7 py-3">
                  <Play size={14} className="text-brand" />
                  Ver Demonstração
                </button>
              </div>

              <div className="flex flex-wrap gap-5">
                {["Configuração em 24h", "Sem código", "LGPD compliant"].map((t) => (
                  <div key={t} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                    <CheckCircle2 size={14} className="text-brand" />
                    {t}
                  </div>
                ))}
              </div>
            </div>

            {/* Right — dashboard mockup */}
            <div className="relative">
              {/* Glow */}
              <div className="absolute inset-0 bg-brand/10 rounded-3xl blur-3xl scale-95 pointer-events-none" />
              <div className="relative">
                <DashboardPreview />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Clients ────────────────────────────────────────────── */}
      <section className="py-10 border-y border-surface-border bg-surface">
        <p className="text-center text-xs font-semibold text-ink-muted uppercase tracking-widest mb-6">
          Confiado por times comerciais de grandes empresas brasileiras
        </p>
        <div className="flex flex-wrap items-center justify-center gap-8 px-6">
          {clients.map((c) => (
            <span key={c} className="text-sm font-bold text-ink-disabled uppercase tracking-wider hover:text-ink-secondary transition-colors">
              {c}
            </span>
          ))}
        </div>
      </section>

      {/* ── Problema ───────────────────────────────────────────── */}
      <section id="problema" className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <p className="section-label mb-3">O Problema</p>
            <h2 className="text-4xl font-extrabold text-ink mb-4 text-balance">
              Reuniões são o maior ativo comercial ignorado
            </h2>
            <p className="text-ink-secondary max-w-xl mx-auto">
              Cada reunião carrega sinais valiosos sobre intenções, riscos e oportunidades. Mas a maioria das empresas os perde.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
            {problemItems.map((item, i) => (
              <div key={i} className="card p-6 hover:shadow-card-md transition-shadow">
                <div className="text-3xl mb-4">{item.emoji}</div>
                <h3 className="font-bold text-ink mb-2 text-sm">{item.title}</h3>
                <p className="text-xs text-ink-secondary leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Solução / Como funciona ────────────────────────────── */}
      <section id="solucao" className="py-24 px-6 bg-surface">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <p className="section-label mb-3">A Solução</p>
            <h2 className="text-4xl font-extrabold text-ink mb-4 text-balance">
              Da transcrição ao insight em 4 etapas
            </h2>
            <p className="text-ink-secondary max-w-xl mx-auto">
              Pipeline automático que converte áudio e texto bruto em inteligência estratégica pronta para decisão.
            </p>
          </div>

          <div className="grid md:grid-cols-4 gap-5 relative">
            {/* connector line */}
            <div className="hidden md:block absolute top-9 left-[12.5%] right-[12.5%] h-px bg-gradient-to-r from-brand/20 via-brand/40 to-brand/20 pointer-events-none" />

            {steps.map((step, i) => (
              <div key={i} className="relative">
                <div className="card p-6 h-full hover:shadow-card-md hover:border-brand/25 transition-all">
                  <div className="flex items-center gap-3 mb-5">
                    <div className="w-10 h-10 rounded-xl gradient-brand flex items-center justify-center flex-shrink-0 shadow-brand-sm">
                      <step.icon size={17} className="text-white" />
                    </div>
                    <span className="text-4xl font-black text-surface-border select-none">{step.number}</span>
                  </div>
                  <h3 className="font-bold text-ink text-sm mb-2">{step.title}</h3>
                  <p className="text-xs text-ink-secondary leading-relaxed">{step.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Benefícios ─────────────────────────────────────────── */}
      <section id="beneficios" className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <p className="section-label mb-3">Impacto</p>
            <h2 className="text-4xl font-extrabold text-ink mb-4 text-balance">
              Benefícios para o seu negócio
            </h2>
            <p className="text-ink-secondary max-w-xl mx-auto">
              Quatro dimensões onde a KOLIA entrega valor imediato para times B2B de alta performance.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
            {benefits.map((b, i) => (
              <div key={i} className="card p-6 hover:shadow-card-md hover:border-brand/25 transition-all">
                <div className={`w-11 h-11 rounded-xl ${b.bg} flex items-center justify-center mb-5`}>
                  <b.icon size={20} className={b.color} />
                </div>
                <h3 className="font-bold text-ink text-sm mb-2">{b.title}</h3>
                <p className="text-xs text-ink-secondary leading-relaxed">{b.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Diferenciais ───────────────────────────────────────── */}
      <section className="py-24 px-6 bg-[#111827]">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-xs font-bold text-brand uppercase tracking-widest mb-3">Diferenciais</p>
            <h2 className="text-4xl font-extrabold text-white mb-4 text-balance">
              Construída para quem decide
            </h2>
            <p className="text-slate-400 max-w-xl mx-auto">
              Não é mais um dashboard. É uma plataforma de inteligência construída do zero para times comerciais.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {differentials.map((d, i) => (
              <div key={i} className="bg-white/5 border border-white/8 rounded-xl p-5 hover:bg-white/8 hover:border-brand/30 transition-all">
                <div className="w-9 h-9 rounded-lg bg-brand/15 flex items-center justify-center mb-4">
                  <d.icon size={17} className="text-brand" />
                </div>
                <h3 className="font-bold text-white text-sm mb-1.5">{d.title}</h3>
                <p className="text-xs text-slate-400 leading-relaxed">{d.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Métricas ───────────────────────────────────────────── */}
      <section id="resultados" className="py-24 px-6 bg-surface">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <p className="section-label mb-3">Resultados</p>
            <h2 className="text-4xl font-extrabold text-ink mb-4">Números que falam por si</h2>
            <p className="text-ink-secondary max-w-xl mx-auto">
              Dados reais de clientes que utilizam a KOLIA no dia a dia comercial.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
            {metrics.map((m, i) => (
              <div key={i} className="card p-8 text-center hover:shadow-card-md hover:border-brand/25 transition-all">
                <p className="text-4xl font-black text-brand mb-2">{m.value}</p>
                <p className="font-semibold text-ink text-sm mb-1">{m.label}</p>
                <p className="text-xs text-ink-secondary">{m.sub}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Testimonials ───────────────────────────────────────── */}
      <section className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <p className="section-label mb-3">Depoimentos</p>
            <h2 className="text-4xl font-extrabold text-ink mb-4">Quem usa, recomenda</h2>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {testimonials.map((t, i) => (
              <div key={i} className="card p-7 flex flex-col hover:shadow-card-md hover:border-brand/25 transition-all">
                <div className="flex gap-0.5 mb-4">
                  {Array.from({ length: t.rating }).map((_, s) => (
                    <Star key={s} size={13} className="text-amber-400 fill-amber-400" />
                  ))}
                </div>
                <p className="text-sm text-ink-secondary leading-relaxed flex-1 mb-6">"{t.text}"</p>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full gradient-brand flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                    {t.name[0]}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-ink">{t.name}</p>
                    <p className="text-xs text-ink-secondary">{t.role} · {t.company}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA Final ──────────────────────────────────────────── */}
      <section className="py-24 px-6 gradient-brand relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,rgba(255,255,255,0.12),transparent_60%)] pointer-events-none" />
        <div className="relative max-w-3xl mx-auto text-center">
          <KoliaLogo variant="horizontal-white" height={36} className="mx-auto mb-8" />
          <h2 className="text-4xl font-extrabold text-white mb-4 text-balance">
            Comece a transformar reuniões em receita
          </h2>
          <p className="text-white/75 text-lg mb-10 max-w-xl mx-auto">
            Mais de 500 reuniões analisadas. R$ 3.2M em pipeline gerado. Seu próximo insight está a um clique.
          </p>
          <button
            onClick={goDash}
            className="inline-flex items-center gap-2 px-10 py-4 bg-white text-brand font-bold rounded-xl hover:bg-white/90 transition-all shadow-2xl text-base"
          >
            Entrar como Diretor Comercial
            <ArrowRight size={17} />
          </button>
          <div className="flex flex-wrap justify-center gap-8 mt-10">
            {["Setup em menos de 24h", "CSV e XLSX prontos para uso", "Suporte dedicado incluso"].map((item) => (
              <div key={item} className="flex items-center gap-2 text-white/70 text-sm">
                <CheckCircle2 size={13} className="text-white/50" />
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="py-8 px-6 bg-[#0a0f1e] border-t border-white/5">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <KoliaLogo variant="horizontal-light" height={22} />
          <p className="text-xs text-slate-600">
            © 2026 KOLIA · Plataforma de Inteligência Comercial by TOTVS · FIAP Challenge
          </p>
        </div>
      </footer>
    </div>
  );
}
