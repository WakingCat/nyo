const ApiService = {
    // Función asíncrona para pedir datos de un minero
    async getMiner(wh, rack, fila, columna) {
        try {
            // Hacemos la petición a la nueva ruta API
            const response = await fetch(`/api/get_miner/${wh}/${rack}/${fila}/${columna}`);

            if (!response.ok) {
                throw new Error('Error de red o servidor');
            }

            // Convertimos la respuesta a JSON y la devolvemos
            return await response.json();
        } catch (error) {
            console.error("Error en ApiService:", error);
            return null;
        }
    }
};