@SPEC-EDGE-001
Feature: Capturas Edge

  Como dispositivo edge (laptop) que clasifica fotos con el modelo optimizado
  quiero enviar cada foto con su evento
  para que queden guardados en AWS sin duplicados y el portal pueda consultarlos.

  Scenario: Guardar una captura nueva
    Given una foto JPEG y un evento válido con capture_id "cap-0001"
    And la clave correcta del dispositivo en X-Device-Key
    When se envía a POST /edge-captures
    Then la respuesta es 201 con el registro
    And la foto queda en S3 como "edge-captures/cap-0001.jpg"
    And existe un registro de "cap-0001" en la base de datos

  Scenario: Rechazar un envío sin clave del dispositivo
    Given una captura válida sin el encabezado X-Device-Key
    When se envía a POST /edge-captures
    Then la respuesta es 401
    And no se guarda nada

  Scenario: Rechazar un envío con una clave incorrecta
    Given una captura válida con una clave equivocada en X-Device-Key
    When se envía a POST /edge-captures
    Then la respuesta es 401
    And no se guarda nada

  Scenario: Reenviar el mismo capture_id
    Given una captura "cap-0001" ya registrada
    When se vuelve a enviar a POST /edge-captures
    Then la respuesta es 200 con el registro existente
    And no se crea otro registro ni otra foto

  Scenario: Guardar y devolver el recorte clasificado
    Given una captura con crop {"x":8,"y":4,"width":40,"height":30}
    When se envía a POST /edge-captures
    Then el registro guarda el recorte
    And GET /edge-captures/cap-0001 lo devuelve en el campo crop

  Scenario: Rechazar un recorte que se sale de la foto
    Given una foto de 64x48 y un crop con x 30 y width 40
    When se envía a POST /edge-captures
    Then la respuesta es 400
    And no se guarda nada

  Scenario: Rechazar una confianza fuera de rango
    Given un evento con confidence 1.5
    When se envía a POST /edge-captures
    Then la respuesta es 400
    And no se guarda nada

  Scenario: Rechazar una clase que el modelo no predice
    Given un evento con predicted_class "bird"
    When se envía a POST /edge-captures
    Then la respuesta es 400
    And no se guarda nada

  Scenario: Rechazar una foto que no es JPEG
    Given una foto PNG
    When se envía a POST /edge-captures
    Then la respuesta es 400
    And no se guarda nada

  Scenario: Consultar las capturas de la más reciente a la más antigua
    Given capturas con captured_at distintos
    When el portal consulta GET /edge-captures
    Then las capturas vienen ordenadas por captured_at de la más reciente a la más antigua
    And cada una trae una image_url firmada que abre su foto

  Scenario: Consultar sin capturas
    Given que no hay capturas
    When el portal consulta GET /edge-captures
    Then la respuesta es 200 con la lista vacía
