// frontend/src/context/ProjectContext.tsx
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';

export interface Project {
    id: string;
    name: string;
    owner: string;
    platform: string;
    status: string;
    website_url: string | null;
    is_live_monitoring_enabled: boolean;
    last_commit_hash: string | null;
    last_commit_message: string | null;
    is_default: boolean;
}

// Three permanent default repositories — always present even when API is offline
const DEFAULT_PROJECTS: Project[] = [
    {
        id: '00000000-0000-0000-0000-000000000001',
        name: 'Bug-Detection-and-Fixing-Model',
        owner: 'sakthivarshans',
        platform: 'github',
        status: 'active',
        website_url: null,
        is_live_monitoring_enabled: false,
        last_commit_hash: null,
        last_commit_message: null,
        is_default: true,
    },
    {
        id: '00000000-0000-0000-0000-000000000002',
        name: 'Diabetes-Prediction-Model',
        owner: 'sakthivarshans',
        platform: 'github',
        status: 'active',
        website_url: null,
        is_live_monitoring_enabled: false,
        last_commit_hash: null,
        last_commit_message: null,
        is_default: true,
    },
    {
        id: '00000000-0000-0000-0000-000000000003',
        name: 'Noether-Duplicated',
        owner: 'sakthivarshans',
        platform: 'github',
        status: 'active',
        website_url: null,
        is_live_monitoring_enabled: false,
        last_commit_hash: null,
        last_commit_message: null,
        is_default: true,
    },
];

interface ProjectContextType {
    selectedProject: Project | null;
    setSelectedProject: (p: Project | null) => void;
    projects: Project[];
    loading: boolean;
    refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextType>({
    selectedProject: null,
    setSelectedProject: () => { },
    projects: DEFAULT_PROJECTS,
    loading: false,
    refreshProjects: async () => { },
});

export function ProjectProvider({ children }: { children: React.ReactNode }) {
    const [selectedProject, setSelectedProjectState] = useState<Project | null>(null);
    const [projects, setProjects] = useState<Project[]>(DEFAULT_PROJECTS);
    const [loading, setLoading] = useState(true);

    const fetchProjects = useCallback(async () => {
        try {
            const data = await api.getRepositoriesList();
            const apiList: Project[] = (data.repositories || []).map((r: any) => ({
                id: r.id,
                name: r.name,
                owner: r.owner || '',
                platform: r.platform || 'github',
                status: r.status || 'active',
                website_url: r.website_url ?? null,
                is_live_monitoring_enabled: r.is_live_monitoring_enabled ?? false,
                last_commit_hash: r.last_commit_hash ?? null,
                last_commit_message: r.last_commit_message ?? null,
                is_default: r.is_default ?? false,
            }));

            // Merge: start with defaults, then add any API repos not already present
            const merged: Project[] = [
                ...DEFAULT_PROJECTS,
                ...apiList.filter(p => !DEFAULT_PROJECTS.some(d => d.id === p.id)),
            ];
            setProjects(merged);

            // Restore previously selected project from localStorage
            const savedId = localStorage.getItem('neuralops_selected_project_id');
            const found = merged.find(p => p.id === savedId);
            if (found) {
                setSelectedProjectState(found);
            } else if (merged.length > 0) {
                setSelectedProjectState(merged[0]);
                localStorage.setItem('neuralops_selected_project_id', merged[0].id);
            }
        } catch {
            // API offline — fall back to defaults so UI always has projects
            setProjects(DEFAULT_PROJECTS);
            const savedId = localStorage.getItem('neuralops_selected_project_id');
            const found = DEFAULT_PROJECTS.find(p => p.id === savedId);
            if (found) {
                setSelectedProjectState(found);
            } else {
                setSelectedProjectState(DEFAULT_PROJECTS[0]);
                localStorage.setItem('neuralops_selected_project_id', DEFAULT_PROJECTS[0].id);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchProjects();
    }, [fetchProjects]);

    const setSelectedProject = useCallback((p: Project | null) => {
        setSelectedProjectState(p);
        if (p) localStorage.setItem('neuralops_selected_project_id', p.id);
        else localStorage.removeItem('neuralops_selected_project_id');
    }, []);

    return (
        <ProjectContext.Provider value={{
            selectedProject,
            setSelectedProject,
            projects,
            loading,
            refreshProjects: fetchProjects,
        }}>
            {children}
        </ProjectContext.Provider>
    );
}

export const useProject = () => useContext(ProjectContext);
