import { useSearchParams } from 'react-router-dom';
import { SubNav, subNavTabClass } from '@/layout/HubPrimitives';
import { useRovingTabList } from '@/lib/use-roving-tablist';
import { StacksTab } from '@/features/config/StacksTab';
import { SkillsTab } from '@/features/config/SkillsTab';
import { McpTab } from '@/features/config/McpTab';
import { AdaptersTab } from '@/features/config/AdaptersTab';
import { HooksTab } from '@/features/config/HooksTab';
import { ModulesTab } from '@/features/config/ModulesTab';
import { GitTab } from '@/features/config/GitTab';

/**
 * Per-project Configuration surface. Shows what tech stacks, skills, MCP
 * servers, hooks, and modules are wired for the active project so a human can
 * SEE the setup without reading YAML/JSON. Each tab is its own module under
 * features/config/; shared table chrome lives in features/config/shared.
 */

type Tab = 'stacks' | 'skills' | 'mcp' | 'adapters' | 'hooks' | 'modules' | 'git';
const TABS: Tab[] = ['stacks', 'skills', 'mcp', 'adapters', 'hooks', 'modules', 'git'];
const TAB_LABEL: Record<Tab, string> = {
  stacks: 'Stacks',
  skills: 'Skills',
  mcp: 'MCP Servers',
  adapters: 'Adapters',
  hooks: 'Hooks',
  modules: 'Modules',
  git: 'Git',
};

export default function ConfigPage() {
  const [search, setSearch] = useSearchParams();
  const raw = search.get('tab');
  const tab: Tab = (TABS as string[]).includes(raw ?? '') ? (raw as Tab) : 'stacks';
  const setTab = (t: Tab) => {
    const sp = new URLSearchParams(search);
    if (t === 'stacks') sp.delete('tab');
    else sp.set('tab', t);
    setSearch(sp, { replace: true });
  };
  const { tabRefs, onKeyDown } = useRovingTabList(TABS.length, (i) => setTab(TABS[i]));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SubNav tablist ariaLabel="Configuration sections">
        {TABS.map((t, i) => (
          <button
            key={t}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`cfgtab-${t}`}
            aria-selected={tab === t}
            aria-controls="cfg-tabpanel"
            tabIndex={tab === t ? 0 : -1}
            onClick={() => setTab(t)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`${subNavTabClass(tab === t)} cursor-pointer`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </SubNav>
      <div className="min-h-0 flex-1 overflow-auto cos-scroll">
        <div
          role="tabpanel"
          id="cfg-tabpanel"
          aria-labelledby={`cfgtab-${tab}`}
          tabIndex={0}
          className="mx-auto w-full max-w-5xl px-6 py-6"
        >
          {tab === 'stacks' && <StacksTab />}
          {tab === 'skills' && <SkillsTab />}
          {tab === 'mcp' && <McpTab />}
          {tab === 'adapters' && <AdaptersTab />}
          {tab === 'hooks' && <HooksTab />}
          {tab === 'modules' && <ModulesTab />}
          {tab === 'git' && <GitTab />}
        </div>
      </div>
    </div>
  );
}
