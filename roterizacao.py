import openrouteservice

# Substitua com sua chave de API
client = openrouteservice.Client(key='WyREn7weXHzxuW9uUpKUbj2H9HIyKog0mPJ-qnhnD2M')

enderecos = [
    "Avenida Belarmino Pereira de Oliveira, 429, Jardinópolis, SP",
    "Rua José Coradine, 358, Jardinópolis, SP",
    "Rua Rui Barbosa, 118, Jardinópolis, SP",
    "Rua Amador Bueno, 5, Jardinópolis, SP"
]

coordenadas = []

for endereco in enderecos:
    geocode = client.pelias_search(text=endereco)
    if geocode['features']:
        coord = geocode['features'][0]['geometry']['coordinates']
        coordenadas.append(coord)
    else:
        print(f"Endereço não encontrado: {endereco}")

# Exibir coordenadas
for i, endereco in enumerate(enderecos):
    print(f"Endereço: {endereco}")
    print(f"Coordenadas: {coordenadas[i]}")
    print()

    async def roterizacaoEntregas():
        lista = []
        for i in range(len(coordenadas)):
            lista.append(coordenadas[i])

        # Chama a função de roteirização com as coordenadas
        # Exemplo de chamada da função de roteirização
        # response = client.directions(
        #     profile='driving-car',
        #     format='geojson',

#     uvicorn.run(app, host="0.0.0.0", port=8000)