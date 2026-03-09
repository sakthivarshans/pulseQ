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
    projects: [],
    loading: true,
    refreshProjects: async () => { },
});

export function ProjectProvider({ children }: { children: React.ReactNode }) {
    const [selectedProject, setSelectedProjectState] = useState<Project | null>(null);
    const [projects, setProjects] = useState<Project[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchProjects = useCallback(async () => {
        try {
            const data = await api.getRepositoriesList();
            const list: Project[] = (data.repositories || []).map((r: any) => ({
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
            setProjects(list);

            // Restore previously selected project from localStorage
            const savedId = localStorage.getItem('neuralops_selected_project_id');
            if (savedId) {
                const found = list.find(p => p.id === savedId);
                if (found) {
                    setSelectedProjectState(found);
                    return;
                }
            }
            // Default: first project in list
            if (list.length > 0) {
                setSelectedProjectState(list[0]);
                localStorage.setItem('neuralops_selected_project_id', list[0].id);
            }
        } catch {
            // API offline — leave empty
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
